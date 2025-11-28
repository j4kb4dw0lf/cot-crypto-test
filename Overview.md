# Context
The aim of the proposed approaches and designs is to enable scanning of different codebases, in this case those written in C/C++, to detect the use of cryptographic routines that are not considered secure in the post-quantum era.
Once these routines are detected, the solution should propose alternative implementations that are considered safer.

The selection of these alternatives is based on NIST and TNO guidelines.


# Approaches
## Approach A
The most used libraries are scraped to extract the most primitives possible, categorize them and propose an alternative if necessary, all those information are stored in a database that can be used then to create the actual query to scan the codebases. 
The following libraries are considered: openssl, libssh, libsodium, libssh2, wolfssl, cryptopp, botan.

### Overview

### Database creation
![ApproachAOverview](https://hackmd.io/_uploads/H1ImXkrJbg.png)
[Lucid link](https://lucid.app/lucidspark/fa954192-b93d-48ab-91b9-d8525d72c48e/edit?viewport_loc=16%2C97%2C2281%2C1248%2C0_0&invitationId=inv_a52dc5b9-170f-4367-a66c-d4116e20db92)

The dashed arrows indicates usage of components used in a new approach of the database creation, explained in the below section: New approach for DB creation.

1. **Git Cloner Module**
Is used to permit to download libraries/git repos and aggregate them to other offline libraries that will be used later by the parser module to extract the primitives.

2. **Parser Module**
Parse the headears of the repos/libraries checking extension like .h, .hpp, .hxx and then it will get information of each function found from the headers as:
function name, namespace, return type, parameters, filepath, line.
The parser is using **LIBCLANG** library.

3. **Category Matcher Module**
- Parse the list of algorithms (aes, blowfish, rsa, etc.), list of operations (encrypt, decrypt, init, sign, etc.), list of PQC algorithms (falcon, dilithium, kyber, etc.)

- A tokenizer will analyze the function's names using delimiters, camelcase, pascalcase to understand if some known algorithms is used.
For example ```CryptoClass::super_AES256``` it will be analyzed as: ```['Crypto', 'Class', 'super', 'AES', '256']```
It will consider the longest match find from the defined algorithms list. (e.g. it will consider aes256 instead of only aes).
- A classifier will use the tokenizer to understand if algorithms/operations are used to then categorize them (e.g. BlockCiphers, StreamCiphers, etc.) and detects also an alternative, if any.

- The module can check also if a function is quantum-safe given the list of algorithms considered safe and the list of PQC algorithms.

4. **DB Builder module**
Using the category match module it will aggregate the information about the primitives with the associated informatiuon as library name, category, parameters, return type, if is quantum safe, alternative etc.


#### Database structure
The first data structure used to aggregate all the information, was a JSON file, but after migrating to a relational database, specifically SQLite, a 30% reduction in processing time was observed.

The following tables were used:

**Libraries**:
Stores the high-level information (name, version, etc.) about each software library you have scanned.

**Categories**:
Stores the found categories and a possible alternative.

**Primitives**:
Stores information about the primitives, the associated library, parameters and if the arguments should be analyzed, if no algorithms names are detected from the primitive name.

**PrimitiveCategories**:
Junction table between primitives and categories.


### Issues with the current design:
- Difficulties in using Clang to detect all primitives:

    - It is necessary to pass compiler arguments, but for some libraries, different arguments are required to successfully compile specific headers or pieces of code.
    - To cover all primitives, the arguments must also be adapted to the architecture being used.
    - The library contains many classes and types that need to be handled (e.g., CursorKind.CXX_METHOD for member functions, CursorKind.CONSTRUCTOR, etc.), and there is a risk that some types might not be considered and there is no generalized way to detect all the required types (constants, variables, function names, class names, etc.).
- Difficulties in detecting complex parameters used by functions:
For example, a struct passed to a generic crypto function, where the struct determines which algorithm to use (including vulnerable ones).

### New approach for DB creation
At the beginning, Clang was used for the creation of the database. However, due to the challenges mentioned earlier, CodeQL was chosen for database creation as well. This brought the following advantages:

- Although CodeQL also has types to handle, it was more manageable and resulted in less complex code.
- Automatic detection of compilation flags, supported by CodeQL.


### Code scanner
Given the database created in the previous step, it's possible to create from it different queries that can run with CodeQL to detect the primitives and propose alternatives, then, reports can be created from the results.

Here an overview of the modules involved for this task:
![ApproachACodeScanner (1)](https://hackmd.io/_uploads/SJbrF04y-e.png)


1. **Query Maker Module**
It will read the collected information from the database, and create 3 types of CodeQL queries:
    - **Query no args**
    For the primitives that is not necessary to analyze the arguments, due is sufficient the primitive's name to understand specifically which algorithm it will be used.
    - **Query args**
    For the primitives that is necessary to analyze the arguments, due the primitive's behaviour i.e the algorithm used cna change based on the values of the passed arguments.
    - **Query Macro**
    The query's goal is to analyze also values define as macros, due some primitives' behaviour are based on some macro's value. 

2. **Report Maker Module**
It gets the BQRS file i.e the CodeQl's raw result, to interpret it and convert it into a SARIF file (JSON-based format), always using CodeQL, then a PDF report is generated to create a more human-readable results.

### Validation: comparing primitives in the DB with libraries' documentation
To determine whether the database contained all the primitives present in the libraries, all the documentation were processed, and each database primitive was searched within the documentation.
The following observations arose:

- Many primitives were present in the documentation but not in the DB
Further explanation of the reasons for this issu is provided in the next section.

- Many primitives were present in the DB but not in the documentation.
That's because many primitives are not intended to be used by the developer.

### Issues with the current design:
#### Lacking primitives
As mentioned before, some primitives were not detected. This happens because, although CodeQL has automatic detection of the compilation flags, it usually does not attempt to enable all possible features. For example, some libraries, like OpenSSL, disable certain features by default if they are considered deprecated or experimental. To compile these features and include them in the database, we need to explicitly pass the necessary flags.

A feasible approach is to create custom build files that use the required flags to enable all available features, allowing us to capture all primitives documented in the library, including experimental or deprecated ones.

#### Detection with lack of generalization
The queries are built based on the classified primitives found in the database.
This results in long queries with many primitives and very strict detection i.e., if a function is not in the database or in the libraries that were scraped (e.g. openssl, libssh, botan, etc.), it will not be detected.


# Approach B
## Post-processing and post-categorization approach
After discovering that CodeQL supports regex matching, it became possible to parse many functions and arguments by detecting patterns. However, this approach can lead to numerous false positives, since it is sufficient for a substring of an algorithm name to appear in the code for it to be flagged. Despite this, it is more flexible compared to the rigidity and lack of generalization of the previous approach.

Previously, the database was structured so that each primitive was associated with a specific categorization (a pre-categorization approach) and a recommended alternative for migrating to a safer algorithm. However, for some primitives, categorization is not possible because their behavior depends on the arguments provided.

Example:
From Botan library is possible to use the primitive create_or_throw and from this primitive is possible to use several algorithms, e.g. ```create_or_throw("AES-256")```, ```create_or_throw("ChaCha(20)")```.

To address the lack of generalization, CodeQL is used with different regex patterns to detect as many vulnerable algorithms as possible, accepting the trade-off of potential false positives.


# Future work
- Use a post-processing module to propose different alternatives for detected primitives that rely on different algorithms (e.g., ```TLS1_TXT_RSA_PSK_WITH_ARIA_256_GCM_SHA384```).

- Create VS Code extension to directly analyze the codebase without the GUI.

- Codebase refactoring

























