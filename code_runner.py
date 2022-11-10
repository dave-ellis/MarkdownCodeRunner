import subprocess
import os
import sys
import threading
import json
import logging

from string import Template

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

verbose_setting = 'code_runner_verbose'
scope_setting = 'code_runner_scope_name'
commands_setting = 'code_runner_commands'
config_tag_setting = 'code_runner_config_tag'
output_tag_setting = 'code_runner_output_tag'

default_scope_name = 'markup.raw.block.fenced.markdown'
default_commands = {
    "sh": "C:\\Program Files\\Git\\usr\\bin\\bash.exe"
}
default_config_tag = "CodeRunnerCONFIG"
default_output_tag = "CodeRunnerOUT"

results_view_name = "Code Runner Results"


class RunCodeCommand(sublime_plugin.TextCommand):
    def __init__(self, view):
        sublime_plugin.TextCommand.__init__(self, view)

        root_settings = sublime.load_settings('CodeRunner.sublime-settings')
        settings = Settings(root_settings, None, verbose_setting)
        self.settings = settings

        self.verbose = settings.get(verbose_setting, False) or None
        self.scope = settings.get(scope_setting, default_scope_name)
        self.output_tag = settings.get(output_tag_setting, default_output_tag)

        logger = logging.getLogger('CodeRunner')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        self.logger = logger

    def run(self, edit):
        view = self.view
        settings = self.settings

        selection = view.sel()
        cur = selection[-1].a
        if view.match_selector(cur, self.scope):
            codeRegion = self.expand_to_scope(cur, self.scope)
            outputRegion = self.locate_output_block(codeRegion)
            text = self.region_text(codeRegion)

            command = ShellCommand(view, edit, settings, text, outputRegion)
            command.capture_args()

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

    def locate_output_block(self, codeRegion):
        outputStart = r"<!--\W*" + self.output_tag + r"\W*-->"
        startRegion = self.view.find(outputStart, codeRegion.b + 1)
        if startRegion.a < 0:
            return None

        fencedRegion = self.view.find(r'^```', codeRegion.b + 1)
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


class Settings:
    def __init__(self, root, root_name, verbose_key):
        self.root = root
        self.root_name = root_name

        self.verbose = root.get(verbose_key)
        logger = logging.getLogger('settings')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        self.logger = logger

    def get_settings(self, key):
        sub_settings = self.root.get(key)
        return Settings(sub_settings, key, 'verbose')

    def get(self, key, default_value):
        value = self.root.get(key, default_value)

        if self.root_name:
            self.logger.debug("Setting: %s.%s=%s", self.root_name, key, value)
        else:
            self.logger.debug("Setting: %s=%s", key, value)

        return value


class ShellCommand(threading.Thread):
    def __init__(self, view, edit, settings, text, outputRegion):
        self.stdout = None
        self.stderr = None
        self.env = os.environ.copy()

        self.edit = edit
        self.view = view
        self.settings = settings
        self.outputRegion = outputRegion

        logger = logging.getLogger('CodeRunner')
        logger.setLevel(logging.DEBUG if settings.verbose else logging.INFO)
        self.logger = logger

        self.shell_commands = settings.get(commands_setting, default_commands)
        self.config_tag = settings.get(config_tag_setting, default_config_tag)

        self.code = ""
        self.script = ""
        self.parameters = []
        self.previous_args = {}
        self.args = {}
        self.config = {}
        self.working_dir = ""
        self.user_input = ""

        self.extract_config()
        self.parse_text(text)

        threading.Thread.__init__(self)

    @staticmethod
    def identify_parameters(script):
        return [
            s[1] or s[2]
            for s in Template.pattern.findall(script) if s[1] or s[2]
        ]

    def extract_config(self):
        configStart = r"<!--\W*" + self.config_tag + r"\W*-->"
        startRegion = self.view.find(configStart, 0)
        if startRegion.a < 0:
            return None

        line = self.view.full_line(startRegion.a)
        start = line.b

        configEnd = r"<!--\W*/" + self.config_tag + r"\W*-->"
        endRegion = self.view.find(configEnd, start)
        if endRegion.a < 0:
            return None

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
                self.config[name] = value

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

        self.parameters = self.identify_parameters(self.script)

        self.logger.debug("working dir: %s", self.working_dir)
        self.logger.debug("parameters: %s", self.parameters)
        self.logger.debug("script: %s", self.script)

    def capture_args(self):
        param = self.find_missing_argument()
        if param:
            prev_arg = self.get_previous_arg(param)
            self.ask_parameter(param, prev_arg)
        else:
            self.run()

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
            self.run()

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

        tail = Tail(3)
        output = ""
        while True:
            line = proc.stdout.readline()
            line = line.strip()
            if line != "":
                tail.add(line)
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
            self.view.replace(self.edit, self.outputRegion, tail.text())

        if output != '':
            self.logger.debug("showing results")
            header = json.dumps(self.args) if self.args else ''

            self.view.run_command('show_results', {
                'header': header,
                'command': script,
                'results': output
            })


class Tail:
    def __init__(self, maximum):
        self.maximum = maximum
        self.size = 0
        self.position = 0
        self.list = [None] * maximum

    def add(self, line):
        self.list[self.position] = line
        if self.size < self.maximum:
            self.size += 1
        self.position = (self.position + 1) % self.maximum

    def text(self):
        text = ""
        start = self.position % self.size
        for i in range(self.size):
            position = (start + i) % self.size
            text += self.list[position] + "\n"

        return text.strip()


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
