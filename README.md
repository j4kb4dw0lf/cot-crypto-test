### Context
The aim of the proposed approaches and designs is to enable scanning of different codebases, in this case those written in C/C++, to detect the use of cryptographic routines that are not considered secure in the post-quantum era.
Once these routines are detected, the solution should propose alternative implementations that are considered safer.

More info: [Overview](Overview.md)

### Usage
1) Run `python ui.py`
2) Choose the workspace and right-click the codebase to open the dialog pane to create the CodeQL's database.
   
   <img width="690" height="502" alt="demo-step-1" src="https://github.com/user-attachments/assets/edfae8f5-6706-49d1-b135-23594948d6a8" />
4) Choose right-click the CodeQL's database to analyze it.
   
   <img width="690" height="502" alt="demo-step-2" src="https://github.com/user-attachments/assets/c2615b5b-7d30-4c33-b667-a68fafb3abb9" />
   
5) The result will be printed.
   
   <img width="690" height="502" alt="demo-step-3" src="https://github.com/user-attachments/assets/acbf98ef-b3a1-4089-9ffb-340519ab957b" />
   
   The SARIF file can be opened by a SARIF viewer (e.g. VS code extension).
   <img width="690" height="502" alt="demo-step-4" src="https://github.com/user-attachments/assets/0411f43a-83aa-4400-8b4a-3b6b6b96303a" />


