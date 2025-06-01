### GUI Option
1) Run `python ui.py`

### CLI Option
#### Scan project
1) Run `python core.py scan-project` having in the same working directory the codeQl's database with folder's name `codeql-db` and having the primitivies' database store in a folder named `DB`.
You will see the different libraries that you have.

2) Run `python core.py scan-project <library id> or any` to analyze the code based on specific (or all) libraries.
The result will be stored in `outputs` folder.

#### Create report
1) Run `python core.py report` to see all the different analysis files stored in the `outputs` folder.

2) `python core.py report <filename>` to generate the PDF report into the `output` folder.
