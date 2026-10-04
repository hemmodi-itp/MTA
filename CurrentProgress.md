

------------------------------------------------------
-------------------------------------------------------
07/06/2026
-*Done

---add thing like application level segeragation, right now application asset is all it being kep in, 

it has to be better so that for app all the data is segerated alike ittens, test_data, scenarions, comphension, 

the current segere agtion is not good


------------------------------------------
-*Done
take a look at, project integration perspective : 

the comprehension engine passes out scnearios and business scenarrios

now finally comprehesnion output  will be used for creating intents/scenarios later on too 
so how uill we create the current scenarions, 

should there be a better way of ecxectuion?
approach one: like if scenatos are produced form comprehsnion execute playwright testsscripts  form scenarions no intents
approach two :  current scenarions to --intent ---to --scenarios ---script like current  

approach three : if there is any list here


lets olan whatn shoulf our plan to eexcute an end to end agent from 

comprehension to test data to test artifacts(intents and scenarios) to ui scanner to  to execution to reporting

make a logical bid what should the entire flow should be ? 

what about the input?  how wdo we provide it centrally. right now comprehension needs . files, test data needs comprehension files  and ui scanner needs url, and test scriot needds the test execution ..lets plan end to end how to manage this agentic project workflow, we could have different workflows for smoke, regession and test creation, 
---------------------------------------
------------------------------------------
-*Done
smoke and regesstion executed the current test execution 
test triggers e

------------------------------------------------------------------
-------------------------------------------------------------------
-*Done
in this the consideration is each module should be independent although they are intera cting, i shouls be in a place where i can extrat the module 

start with module bifurcation. 

What needs to be achived 
Each module should be independent, Comprehension, Test Data Generea

-----------------------------------------------------
--------------------------------------------------------
-*Done
close the browser in finally after UI Scanner and Test Execution.

the process should ultimately be three modules in parallel like websirevcies which expect certai inputs and extract and output like a request response, 


--------agent conifg --- confif/
-*Done
agent
agent.yaml
settings.xml
these should not be here any more should go in worflow somewhere
because like project.yaml these are also in a way inptu files. 


--------------------------------------------------
-------------------------------------------------
-*Done
Workflow time of each agent and module is high need to optimise
Project not organised in terms of scalability, each needs to be at one place only not in every agent --

the directory should be project based in application_assets projects contain information of all the stuff it is integrated to

input/comprehension_inputs should also go to application_assets further into 

key distibutions are  : 
Model Level Comprehension, Test Data and Script and Test Execution are all three different modules. 
Than next segregation is based on project , 
each project shiuld its own artifacts like intents, test data, input, output everything, 

and agents should have the flexibilty to be called from any project
agents are reusable for all orjects
but agnt structure remains intact

The orchestrator chooses which one/two or all to execute based on the input workflow

which is due to follow project architecture there in
---------------------------------------
-*Done

add logs into each process: 
add logs for output files, of each agent 
some identifies in agent completion like 
add logs for each step in testcases as well, like this was executed, this paased, response

-----**------
-*Done
also print the headless true false before execution and ui scanner 

-----------------------
-*Done
i think instead of repeating in project it shoukd be outside in the projects, a read md for the orject like how to write projects and their inner files: 

--------------------
--------------------
-*Not Done
in this the consideration is each module should be independent although they are intera cting, i shouls be in a place where i can extrat the module a

-----------------------
-*Not done 09/06
usage of healing agent with a new work flow, 
NS integration
reporting agent update to json and html files

--------------------------------
-*Done ---> reporting
reporting agent update to json and html files
------------------------------------------ 
----------------------------
-*_Done
Project Memory Plan

-*_Done
read md files to decide what should be stored and added to the new artifacts


-----------------------------------------------
-----------------------------------------------
-*_Done
--- Store the testcase.
---only update not hard rewrite
---add more test artifacts when needed. 
---create a capability of scanning current code --before ui scanner, because we dont want to execute the same things again and again -


-----------------------------------------------
----------------------------------------------
-*_Plan

---create an agent for CI/CD connection and push changes.
--integrate healing system for existing and new code
--NS Integration
--FE and its components
--APP Evolve Integration

-------------------------------------------------
----------------------------------------------------

-*_Done
Grep "dispatch|external" (in c:\Users\DeepakAhlawat(CloudP\Documents\Projects\agentic-qa-platform\agents\orchestrator\orchestrator_agent.py)
9 lines of output
Read c:\Users\DeepakAhlawat(CloudP\Documents\Projects\agentic-qa-platform\orchestrator\contracts.py

create a logging style to clearly mark the heading via passing whatever is availbe agent name, step name, execution type, anfdlike all the logs have a heading after 3 for lines or two lines


------------------------------------
-------------------------------------
-*_Done
wait_until="commit" → "networkidle" in playwright_scanner.py:340 (sauceDemo DOM scan finds 0 elements)



-------------------------------------------------------------
-----------------------------------------------------

-*_NotDone
frontend display using a basic html ui on local host : 3000
need to integrate the ns fallback and integration to the cpre. 
like respose and all should be valdiated and read 

project wise, saving and re execution
frontend display and integratig with AppEvolve



------------------------------------------------
------------------------------------------------
-*_NotDone

Add wiki details
about the project in proper structure
---------------------------------------------
-----------------------------------------------
-*_Done

--- do we read the md files beforec creating any decisio about the test data and test scenarios like for the ideas and consistency 

like add a couple of testcases/ scenarions/ test data /test intent/ as few shot example of what has to be created, and share what else is needed. 

like for example, I wan that when scenarios are prepared, i want the firat scenario to be click on different menu tabls, 
Second to include the input fiels, and fill in them -- like login/ search / registration
third to be input field again and choose againn from  search /registration....




----------------------------------------------------------------------------------
------------------------------------------------------------------------------------
-*_Done

moderinize api usage
reduce the api, make agentic system more efficient.

--------------------------------------------------------------------------------------------------------------

update the NS Integrations
-----------------------------------------------------
Create tests for appevolve


-----------------------------------------------------
-------------------------





--------------------------------------
-* Not Done
add an validation tool, check what kind of tools /guardrails are already there for validating the llm resepobse, like the result is right specially in terms of scenarion from comprehension , 

test data credibiltiy and test scripts , we need to add validators 

different validators for different agesnts ...like comprehsenion valdiator should check all busnness areas are covered, no topic missing, prose level aal things are considered. 

Positive negative all test casea e covered

test data to cehck if test data is matching the scenarion based on the [roject type should we check some more cases ]

scenario generator to check all intents are duly consideed.

-------------------------------------------------------
-----------------------------------------------------

agentify Legacy Leap

add picture compatibility in input 

time to add API testing? 

play and record record ready.  

-----------------------------------------------------
--------------------------------------------------------


-*_ Done

Remove execessive test creations - negative and boundary cases limited. 

-*_ Done
login set up for module to be kept in project.yaml only.

---------------------------------------------------

-*_Not Done
Still execessive test creations happening. 
We must add a few shot example to limit the number of testscases. 
Add some kind of risk factor to each testcase to decide whether it has to be created or not. 

Interaactive scan is not capturing the details anymore. We need to re create it. 



--------------------------------------------

-*_Not Done

1. All locators in one place. 
2. Closing the browser thrive while execution should move it to headless mode... not working

3. we must improve the no llm fallback to also consider the module id if no llm is found and syntheytic testcases are created..
The synthetic scenario generatpr should also be just like a normal scenario generatpor would create.   


--

Move locator map to module wise
locator_map.json should be in comprehension beside the artifact_registry
in comprehension root folder
_*_Done. refactor folders to test_comprehension, test_execution in the template folder ---
-create new workflows for all process inlcluding reporting
-rename execution to test execution in geeration agent
--create different test_suites, and tests should be added to them, we will execute those from workflows.
--why extract json reports?
--Contracts, orchestrator, logs?, execution, json reports,  
--3 close moves execution in headless
