# CodeRunner

Runs code in fenced blocks.


## Installation

The plugin is tested on Windows and Linux but should also work on macOS.
To install it from https://packagecontrol.io/ do the following:

1. Open the command palette and find "Package Control: Install Package"
2. Search for CodeRunner and install.

To install from GitHub do the following:

1. Locate Sublime Text packages folder by choosing the menu:
    ```
        Preferences -> Browse Packages...
    ```
2. Clone or download git repository into a new folder named "CodeRunner" under the packages folder


## Configuration

All configuration is available through the menu:
```
    Preferences -> Package Settings -> CodeRunner
```
This includes

* Default settings which can be copied into the user settings and then changed
* Default keymap which can overridden in the user keymap


## Usage

Supported fenced code blocks are identified and may be executed.  

A code block may contain parameters which are identifiers which start with `$` and may be wrapped with 
braces.  Parameters are identified and populated, either from an optional CONFIG block 
or via an input panel.

Example CONFIG block:

    <!-- CodeRunnerCONFIG -->
    * project_dir=/users/name/working/projectx
    <!-- /CodeRunnerCONFIG -->

Example fenced code block:

    ## Run tests   
    ```sh
    #/some/dir
    go test ./...
    ```

Executing a code block will create an output file in the configured subdirectory, eg.:

    .CodeRunner/CurrentPageName/HeaderID/${timestamp}.out


## CONFIG block

Each page may have one config block which will be used by all code blocks when they are 
executed.

Any parameters not set will be asked for on each execution of a code block.


## OUT block 

Each code block may optionally be followed by an OUT block which will be updated on each execution.

Example code block with an OUT block:

    ## Run Tests   
    ```sh
    cd ${working_dir}
    go test ./...
    ```
    <!-- CodeRunnerOUT{tail=1} -->
    * [Output File](.CodeRunner/PageName/Run_Tests/20221031T125313.out)
    ```
    ok github.com/packagex
    ```
    <!-- /CodeRunnerOUT -->

### OUT Block Options

| Option      | Default | Description                                      |
|-------------|---------|--------------------------------------------------|
| head=n      | -       | updates the block to include the first `n` lines |
| tail=n      | 5       | updates the block to include the last `n` lines  |
| filter=text | -       | if set, filters the output                       |


## HISTORY block

Each page may have one history block which is normally located at the bottom of the page 

If this block exists, then it will be updated each time a code block is executed.

Example history block:

    <!-- CodeRunnerHISTORY{keep=10} -->
    * 2022-10-31:
        - 13:35:51 [Run Tests](.CodeRunner/PageName/Run_Tests/20221031T125313.out)
        - 13:45:32 [Run Tests](.CodeRunner/PageName/Run_Tests/20221031T134532.out)
        - 16:01:51 [Run Tests](.CodeRunner/PageName/Run_Tests/20221031T160151.out)
    <!-- /CodeRunnerHISTORY -->

### HISTORY block parameters

| Name | Default | Description                                                       |
|------|---------|-------------------------------------------------------------------|
| keep | 20      | Limits the total count of history elements to the supplied number |


## Supported Types of Fenced Blocks

| Type | Notes                                            |
|------|--------------------------------------------------|
| sh   | Shell code blocks are executed as a shell script |


## Default Key Map

In markdown contexts (using the default keymap) the following shortcuts are available.

| Shortcut        | Command   | Description                                                     |
|-----------------|-----------|-----------------------------------------------------------------|
|  `ctrl+shift+r` | run_block | Executes the run block command against the current fenced block |
|  `ctrl+shift+m` | ask_menu  | Allows the user to select from list of commands                 | 


## Settings

For details see the keymap file available through the menu:
```
    Preferences->Package Settings->CodeRunner* menu.
```


## Tasks

* [x] Use a configurable shell command to support different environments
* [x] Run a single line shell code command
* [x] Handle supplying the working directory
* [x] Display the results in new view
* [x] Identify, request and inject parameters
    * [x] Identify required parameters
    * [x] Ask for parameters that are missing
    * [x] Inject parameters to script
    * [x] Convert parameter name to a label
    * [ ] Use previous parameter value as initial value
* [x] Support configuration block
    * [x] Extract settings
    * [x] Supply settings as parameters to script
* [x] Record script and parameters in results
* [ ] Support output block
    * [x] Support updating / replacing output section
    * [x] Handle missing output block
    * [ ] Support `tail=n`
    * [ ] Support `head=n`
    * [ ] Support `filter=text`
* [ ] Handle multi-line code block
    * [ ] Create and run temp shell file
* [ ] Support history block
    * [ ] Name code block based on closest header
    * [ ] Record results to timestamped file
    * [ ] Append to history block reference to result file
    * [ ] Support `keep=n` option and limit to latest `n` runs
* [ ] Advanced parameters
    * [ ] Deduce directory and file types with validation and selection dialog 
* [ ] Display menu and run selected code block
* [ ] Progressively update results view as output is generated


## Bugs

* Separate fenced blocks merge together if they are only separated by white-space 


## Future 

* Support for python code blocks
* Support for http code blocks


## Releases

* 0.1.0: Initial version
