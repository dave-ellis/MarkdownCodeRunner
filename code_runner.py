import subprocess
import os
import sys
import threading
import json
import logging

import sublime_settings
import tail

from string import Template
from datetime import datetime

try:
    import sublime
    import sublime_plugin

    # fake the path to prevent the following issue in ST3
    #     ImportError: No module named '...'
    sys.path.append(os.path.dirname(os.path.realpath(__file__)))

except ImportError:  # running tests
    from tests.sublime_fake import sublime
    from tests.sublime_fake import sublime_plugin

    sys.modules['sublime'] = sublime
    sys.modules['sublime_plugin'] = sublime_plugin

verbose_key = 'code_runner_verbose'
scope_key = 'code_runner_scope_name'
commands_key = 'code_runner_commands'
config_tag_key = 'code_runner_config_tag'
output_tag_key = 'code_runner_output_tag'

default_scope_name = 'markup.raw.block.fenced.markdown'
default_commands = {
    "sh": "C:\\Program Files\\Git\\usr\\bin\\bash.exe"
}
default_config_tag = "CodeRunnerCONFIG"
default_output_tag = "CodeRunnerOUT"

results_view_name = "Code Runner Results"


def load_settings():
    root = sublime.load_settings('CodeRunner.sublime-settings')
    return sublime_settings.Settings(root, None, verbose_key)


class RunCodeCommand(sublime_plugin.TextCommand):
    def __init__(self, view):
        sublime_plugin.TextCommand.__init__(self, view)

        self.settings = load_settings()

        self.verbose = self.settings.verbose
        self.scope = self.settings.get(scope_key, default_scope_name)
        self.config_tag = self.settings.get(config_tag_key, default_config_tag)

        self.edit = None
        self.config = {}
        self.parameters = []
        self.previous_args = {}
        self.args = {}
        self.codeRegion = None
        self.text = ''
        self.user_input = ''

        logger = logging.getLogger('CodeRunner')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        self.logger = logger

    @staticmethod
    def identify_parameters(script):
        return [
            s[1] or s[2]
            for s in Template.pattern.findall(script) if s[1] or s[2]
        ]

    def run(self, edit):
        self.edit = edit

        selection = self.view.sel()
        cur = selection[-1].a
        if self.view.match_selector(cur, self.scope):
            now = datetime.now()
            self.args = {'timestamp': now.strftime("%Y-%m-%dT%H:%M:%S")}

            self.codeRegion = self.expand_to_scope(cur, self.scope)
            self.text = self.region_text(self.codeRegion)

            self.config = self.extract_config()

            self.parameters = self.identify_parameters(self.text)
            self.logger.debug("parameters: %s", self.parameters)
            self.capture_args()

    def extract_config(self):
        config = {}

        configStart = r"<!--\W*" + self.config_tag + r"\W*-->"
        startRegion = self.view.find(configStart, 0)
        if startRegion.a < 0:
            return config

        line = self.view.full_line(startRegion.a)
        start = line.b

        configEnd = r"<!--\W*/" + self.config_tag + r"\W*-->"
        endRegion = self.view.find(configEnd, start)
        if endRegion.a < 0:
            return config

        line = self.view.full_line(endRegion.a)
        end = line.a - 1

        configText = self.view.substr(sublime.Region(start, end))
        self.logger.debug("found config block:\n%s", configText)

        lines = self.view.split_by_newlines(sublime.Region(start, end))
        for line in lines:
            text = self.view.substr(line)
            parts = text.split("=", 1)
            if len(parts) == 2:
                name = parts[0].split()[-1]
                value = parts[1]
                self.logger.debug("extracted config: %s='%s'", name, value)
                config[name] = value

        return config

    def expand_to_scope(self, point, scope):
        region = self.view.full_line(point)

        # expand to previous lines that include the scope
        start = region.a
        while start > 0:
            line = self.view.full_line(start - 1)
            if self.view.match_selector(line.a, scope) is False:
                break
            start = line.a
            region = region.cover(line)

        # expand region to following lines which include the scope
        size = self.view.size()
        end = region.b
        while end < size:
            line = self.view.full_line(end + 1)
            if self.view.match_selector(line.a, scope) is False:
                break
            end = line.b
            region = region.cover(line)

        # region = self.view.split_by_newlines(region)

        self.logger.debug("found scope: %s", region)
        return region

    def collect_text(self, regions):
        text = ""
        for region in regions:
            text += self.region_text(region)

        return text

    def region_text(self, region):
        text = ""
        lines = self.view.line(region)
        for line in self.view.split_by_newlines(lines):
            text += self.view.substr(line) + '\n'

        return text

    def capture_args(self):
        param = self.find_missing_argument()
        if param:
            prev_arg = self.get_previous_arg(param)
            self.ask_parameter(param, prev_arg)
        else:
            self.start_process()

    def find_missing_argument(self):
        for param in self.parameters:
            if param not in self.args and not self.use_config(param):
                return param

        return None

    def use_config(self, name):
        if name not in self.config:
            return False

        value = self.config[name]

        self.logger.debug("using config %s=%s", name, value)
        self.args[name] = value
        return True

    def get_previous_arg(self, param):
        if param in self.previous_args:
            value = self.previous_args[param]
            self.logger.debug("found previous arg: %s=%s", param, value)
            return value
        else:
            return ''

    def ask_parameter(self, param, initial):
        self.logger.debug("asking for param: %s", param)
        self.param = param

        label = ' '.join(param.split('_')).title()

        win = self.view.window()
        win.show_input_panel(
            label,
            initial,
            self.on_done,
            None,
            None
        )

    def on_done(self, text=""):
        self.logger.debug("received arg: %s=%s", self.param, text)
        self.previous_args[self.param] = text
        self.args[self.param] = text

        param = self.find_missing_argument()
        if param:
            self.ask_parameter(param, '')
        else:
            self.start_process()

    def start_process(self):
        self.view.run_command('monitor_process', {
            # 'settings': self.settings,
            'config': self.config,
            'args': self.args,
            'text': self.text,
            'blockEnd': self.codeRegion.b
        })


class MonitorProcessCommand(sublime_plugin.TextCommand):
    def __init__(self, view):
        sublime_plugin.TextCommand.__init__(self, view)

    def run(self, edit, config, args, text, blockEnd):
        settings = load_settings()

        cmd = ShellCommand(
            view=self.view,
            edit=edit,
            settings=settings,
            config=config,
            args=args,
            text=text,
            blockEnd=blockEnd,
        )
        cmd.run()


class ShellCommand(threading.Thread):
    def __init__(self, view, edit, settings, config, args, text, blockEnd):
        self.stdout = None
        self.stderr = None
        self.env = os.environ.copy()

        self.edit = edit
        self.view = view
        self.settings = settings
        self.config = config
        self.args = args

        logger = logging.getLogger('CodeRunner')
        logger.setLevel(logging.DEBUG if settings.verbose else logging.INFO)
        self.logger = logger

        self.shell_commands = settings.get(commands_key, default_commands)
        self.output_tag = settings.get(output_tag_key, default_output_tag)

        self.code = ""
        self.script = ""
        self.working_dir = ""

        self.outputRegion = self.locate_output_block(blockEnd)
        self.parse_text(text)

        threading.Thread.__init__(self)

    def locate_output_block(self, blockEnd):
        outputStart = r"<!--\W*" + self.output_tag + r"\W*-->"
        startRegion = self.view.find(outputStart, blockEnd + 1)
        if startRegion.a < 0:
            return None

        fencedRegion = self.view.find(r'^```', blockEnd + 1)
        if fencedRegion.a > 0 and fencedRegion.a < startRegion.a:
            return None

        line = self.view.full_line(startRegion.a)
        start = line.b

        outputEnd = r"<!--\W*/" + self.output_tag + r"\W*-->"
        endRegion = self.view.find(outputEnd, start)
        if endRegion.a < 0:
            return None

        line = self.view.full_line(endRegion.a)
        end = line.a - 1

        outputRegion = sublime.Region(start, end)
        text = self.view.substr(outputRegion)

        self.logger.debug("found output block:\n%s", text)
        return outputRegion

    def parse_text(self, text):
        self.logger.debug("parse text:\n%s", text)

        lines = text.splitlines()
        if not lines:
            return

        # drop fencing (first and last lines)
        first_line = lines[0]
        if first_line.startswith('```sh'):
            lines = lines[1:-1]

        self.code = "\n".join(lines)

        # extract working directory if set
        first_line = lines[0]
        if first_line.startswith("#"):
            self.working_dir = first_line[1:]
            self.config["working_dir"] = self.working_dir
            lines = lines[1:]

        self.script = " ".join(lines)

        self.logger.debug("working dir: %s", self.working_dir)
        self.logger.debug("script: %s", self.script)

    def run(self):
        script = self.script
        if self.working_dir:
            script = "cd " + self.working_dir + ";" + script

        command_template = Template(script)

        self.logger.debug("args: %s", self.args)
        script = command_template.substitute(self.args)
        self.logger.debug("running: %s", script)

        shell_command = os.path.realpath(self.shell_commands['sh'])

        shell_dir = os.path.dirname(shell_command)
        shell_basename = os.path.basename(shell_command)

        os.chdir(shell_dir)
        proc = subprocess.Popen(
            [shell_basename, "-c", script],
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            env=self.env
        )

        buffer = tail.CyclicBuffer(3)
        output = ""
        while True:
            line = proc.stdout.readline()
            line = line.strip()
            if line != "":
                buffer.add(line)
                output += line + "\n"

            return_code = proc.poll()
            if return_code is not None:
                self.logger.debug('Return Code: %i', return_code)
                break

        # Process has finished, read rest of the output
        for line in proc.stdout.readlines():
            line = line.strip()
            if line != "":
                output += line + "\n"

        if self.outputRegion:
            self.view.replace(self.edit, self.outputRegion, buffer.text())

        if output != '':
            self.logger.debug("showing results")
            header = json.dumps(self.args) if self.args else ''

            self.view.run_command('show_results', {
                'header': header,
                'command': script,
                'results': output
            })


class ShowResultsCommand(sublime_plugin.TextCommand):
    def __init__(self, view):
        sublime_plugin.TextCommand.__init__(self, view)

    def run(self, edit, header='', command='', results=''):
        # Get new view for results
        results_view = self.results_view(edit)

        results_view.set_read_only(False)

        if header:
            results_view.insert(edit, results_view.size(), header + "\n---\n")

        results_view.insert(edit, results_view.size(), "> " + command + "\n\n")
        results_view.insert(edit, results_view.size(), results)
        results_view.insert(edit, results_view.size(), "---\n\n\n")

        results_view.set_read_only(True)

    def results_view(self, edit):
        win = self.view.window()

        for view in win.views():
            if view.name() == results_view_name:
                return view

        results_view = win.new_file()

        # Configure view
        results_view.set_name(results_view_name)
        results_view.set_scratch(True)

        results_view.settings().set('line_numbers', False)
        results_view.settings().set("draw_centered", False)
        results_view.settings().set("word_wrap", False)

        # win.focus_view(results_view)
        win.focus_view(self.view)

        return results_view
