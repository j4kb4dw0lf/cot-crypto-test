### Context
The aim of the proposed approaches and designs is to enable scanning of different codebases, in this case those written in C/C++, to detect the use of cryptographic routines that are not considered secure in the post-quantum era.
Once these routines are detected, the solution should propose alternative implementations that are considered safer.

More info: [Overview](Overview.md)

### Prerequisites
The `fpdf` module is required and can be installed with pip: `pip install fpdf`

### Usage VS Code Extension
1) You can run the extension going to the root folder with ```code --extensionDevelopmentPath "%cd%\vscode-extension"``` for Windows environment or ```code --extensionDevelopmentPath "$(pwd)/vscode-extension"``` for Linux environment.
2) Add the folder with the codebase to analyze with the "Explorer" pane.
3) Go to the extension and run "Pre-generate QL Queries" action. It will print also where those queries are generated.
Note: `query_macro.ql`, `query_noargs.ql`, `query_withargs.ql` are the queries to test "Approach A" mentioned in the Overview file.
The other .ql files use regex and lead to better results.
5) Run "Create CodeQL Database", choose the codebase and where to save the generated database.
6) It will ask for the build command. If skipped, CodeQL can try to detect automatically which commands are needed, but it can often fail.
It is recommended to know which command is needed to build the codebase. If multiple commands are required, it is recommended to create an .sh/.bat file with the build steps and provide the script’s path as the build command.

For example, for krb5 in a Windows environment, some additional steps are required. A realistic shell script to build the codebase could look like the following:
```sh
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64
cd C:\krb5-1.21.3\src
set PATH=%PATH%;C:\Program Files\Git\usr\bin
nmake clean
nmake -f Makefile.in prep-windows
nmake NODEBUG=1 NO_LEASH=1
```
Assuming that the shell script is stored in `C:\krb5-1.21.3\build.bat`, it is enough to specify this path when prompted.

If the codebase to be analyzed is not owned, it is recommended to check the codebase documentation/guide to understand which steps are necessary to compile it.

Note:
Database creation can take a while. Check the VS Code Terminal tab (not to be confused with the Output tab) to see the live logs.

6) After creating the database, “Run CodeQL Analysis” and then with "Load SARIF" if possible to see the results.

### Usage GUI
1) Run `python ui.py`
2) Choose the workspace and right-click the codebase to open the dialog pane to create the CodeQL's database.
   
   <img width="690" height="502" alt="demo-step-1" src="https://github.com/user-attachments/assets/edfae8f5-6706-49d1-b135-23594948d6a8" />
4) Choose right-click the CodeQL's database to analyze it.
   
   <img width="690" height="502" alt="demo-step-2" src="https://github.com/user-attachments/assets/c2615b5b-7d30-4c33-b667-a68fafb3abb9" />
   
5) The result will be printed.
   
   <img width="690" height="502" alt="demo-step-3" src="https://github.com/user-attachments/assets/acbf98ef-b3a1-4089-9ffb-340519ab957b" />
   
   The SARIF file can be opened by a SARIF viewer (e.g. VS code extension).
   <img width="690" height="502" alt="demo-step-4" src="https://github.com/user-attachments/assets/0411f43a-83aa-4400-8b4a-3b6b6b96303a" />


