# AI Prompts — Assignment 5

## Problem 1

### Problem Number and Title
Problem 1: Vibe coder prompts

### Main Prompt
Create AI_prompts.md 

Create 10 sections, labelled Problem # (replace # with 1-10)
Under each section, put sub sections

-Problem Number and Title 
-Main Prompt 
-Follow Up Prompt 
-Follow Up Prompt Explanation

---

## Problem 2

### Problem Number and Title
Problem 2: Study the campus customs database

### Main Prompt

open campus_customs.db and summarize them into tables I can read here on this interface. 

Copy campus_customs.db, and rename it campus_customs_new.db. Do not at any time, update the original unless asked. Always update the copy. 

Create output/harness.md. For each table within the database, add a one-liner on what makes that table important for the agents. Recall the notes I gave you earlier too. 

### Follow Up Prompt
Update the "database tables and why they matter section so it's more human readable, and remove the table format. Should be: 
[table name] 
   [why it's important]

### Follow Up Prompt Explanation
It made the harness file a table, so I asked for text

---

## Problem 3

### Problem Number and Title
Problem 3: Build the MCP Server 

### Main Prompt

in the mcp_server folder, create an mcp server using fastMCP. Remember, it should only talk to the new database, and not the oriignal. Let's wait to connect or run the server until later. Please add these 3 tools to the server

2. Restock tool
adds reprinted items to inventory once their bill is paid.
This should help ticket 101 (since inventory shows 0) and tickets similar so please adjust tool to do that
1. Balance check tool
shows what cash would be left after paying the bills that are due to help with asset management
This should help ticket 102 and similar tasks
3. Partial-order tool
Let's add a coupon/discount rate later but for now let's add the ability to do partial shipments ships part of an order now and records the rest as still owed. Notify the user that the shipment will be broken into two parts. The inventory shows 8 when ordering 20
This is meant to help 103.
Take what I've given you, and add them in a tool section in harness.md with 

which table it reads, which ticket it helps (101, 102, 103), and one shortneed sentence on why the tool is the right one for the ticket i've mentioned. 

In the README.md, explain the reason of the mcp server, the database file, and the 3 tools we're adding

---

## Problem 4

### Problem Number and Title
Problem 4: Add the MCP server to vibe coder and test each tool

### Main Prompt
Make sure that the MCP and this project are connected so that the vibe coder can call the tools. That connection JSON should be saved in .mcp.json. 

Let's test each tool. 
1. Let's test restock. Simulate an order for hoodies larger than the quantity avaiable. check if inventory updates 
2. let's say we get an email saying rent is due in 2. Simulate that.  Run a balance check. 
3. Simulate an order of 20 sweatshirts of one kind when there's a lesser inventory. Show me what that would like that. 

## Problem 5

### Problem Number and Title
Problem 5: Build the agent team and grow the MCP tools

### Main Prompt
Let's add pydantic agents, using gpt-6-luna only. 

Boss: Will read each ticket, decide who should work on it, and makes final calls. He should also make final decision calls on tie breakers. 
Inventory: checks stock by SKU and size, spots shortfalls, and which vendor can restock and 
Accounting - responsible for cash and involves, cehcks margins, prepares payments, purchaes orders for human approval 
Facilities - handles the shop space side (leases, rent, etc.)
Customer Service - drafts (not sneds) messages for customers. Do not email customers or contact real vendors. Drafts always stay on the board

They should also be able to talk to each other, and work with each other to not duplicate tasks. 

Take the shop rules I gave you earlier. 

Combined, add the agent prompts in backend/prompts/, creating one file per agent. 

The datatypes should go into backend/models.py

and files should go under backend/. 

Facts should always come from customs_new

Add more tools that you may need to get this shop to function. Do not ever invent a secon ship-tools layer to bypass the MP. An example would be the ability to add discounts and promotions like we talked about earlier. 


As the agents run, they should add the agent loops step and information like our previous sessions to output/audit-traio.json

In the harness file, list each agent, mcp tool (all the ones we previously had, and the new ones)

* add a safety section so that (1) the agent should never interact with the customers outside their direct responsibiliteis, and always ask for approval before handling oney. Anything that sounds like it can harm the business, pease flag. Also make sure that users can't spam the bots and always find the most effective way to do something. Never actually interact with the money or send money back. these approvals reui
* Only draft, never send anything out with your email. 
*  If the token is getting expensive, let the manager know. 


Update README so that the tool list matches our update tooledkit

---

## Problem 6

### Problem Number and Title
Problem 6: Plan the three tickets

### Main Prompt

Create output/desk_tickets.html that will outlay the tickets. There should be a page you can double-click with one tab per ticket (101-103). There should also be emtpy (cash and reflection) tabs that just show a "coming later" note. For each ticket tab, add an "expected section" and "actual section". In the expected section: 
- the boss should call inventory first, to outline if there any issues right away with inventory and the product line itseld. 
- The boss will first read the ticket, check what is needed. delegations: after inventory, the boss will call an agent IF needed, cycle through the agents until its done. Have the boss reassess if no outcome is reached, and reach outo tmajid 

### Follow Up Prompt

> “The Expected sections don’t list the MCP tools

### Follow Up Prompt Explanation
The AI left out the MCP tools initially 

---

## Problem 7

### Problem Number and Title
Problem 7: Backend routes

### Main Prompt
Let's create the react front end. It'll need a backend - backend/main.py. Use FASTAPi and it should do the following: 

outputt thr 3 ticket sand the their statuses 
tahe a ticket id and run your agent team on that ticket 
return recent agents events and record what agents said and what tools were accessed. 
Prompt me to approve a payment 
the balance from cash_accounts is what?
The server should start with uvicorn main:app --reload --port 8000

---

## Problem 8

### Problem Number and Title
Problem 8: Agent dashboard

### Main Prompt

Let's build the dashboard. It should use react, vit, typescript. 

include an d call all the previous routes we established. 
the dashboard should list all tickets
let admin pick one ticket to start the agent team to start with 
Show what each agent is doing as the ticket runs, and how they're speaking to each other. THis should be visually amazing, with round indiciators that light up and stay green (from red, yellow) as progress is made. 
Mark the ticket resolved when the run finishes, with a summary of what each agent did to resolve the ticket. 
Prompt a human to approve a pay or purchase when needed 
Show the checking balance, as a ticker on the top right corner. 


The front end should be able to talk to the backend for all the info at localhost:8000. For the backend, vite page oriign access is granted to allow calling the routes. 

The board site should be able to run with npm run dev. 


output/design.md is where we put all out designs and is a reference for how the dash should look. 
a 80's retro bit-interface, yet sleek and elegant. Nothing punchy. 
colors: blue, grey mostly but can be other colors too
the front page should have a summary of everything needed to tell a snapshot of where things are and what agents are working, how many tickets. 
There should be tabs that populate for each ticket. 
Make the inteferace like a game for the user
Each agent should have a icon (bit-looking) with different colors that are consistent for their text and summaries. They should hav etheir own personailiyes. The boss should be like bowser from mario. The others should be humonoid. 
there should be a leaderboard tab with stats of each agents performance. 
everyime a ticket closes, there should be fireworks and a sound effect.  

### Follow Up Prompt

can you open the site in a browser
### Follow Up Prompt Explanation
It didn't show me 

---

## Problem 9

### Problem Number and Title
Problem 9: Resolve the tickets

### Main Prompt

FIrst, let's reset the _new database to match the original. 

Call out the starting checking balance. 

Open the dashboard, and run all 3 tickets until each is resolved. 

In desk_tickets, fill out the "actual" section with 
- which agents worked
- what they delegated 
- which tools were used 

In desk_tickets, fill out the cash tab: 
- the starting balance we noted
- how the cash changed when the ticket was resolved, for each ticket and why (which pay/ purchase AND dollar amount)
- ending chcking balance. Note if this is different than the cash_accounts in the wroking db

update output/resolved_tickets.json for each ticket: 
- the id 
- final status 
- outcome summarized 
- what each agent contrinuted 
- and if a human approvals were needed, and what it was 

update resolved_board.html 
- this is a page that shows a screenshot of each resolved ticket, and lets you double click with a screenshot. 

These real runs should be updated in audit trail json. 

Add all necessary info in the hardness so it has the tables, mcp tools, all the agents, the api routs, dashboards, and rules we added. 

---

## Problem 10

### Problem Number and Title
Problem 10: Reflection 

### Main Prompt

Add the following in the reflection tab for desk_tickets.html 


Agent evaluation: 
- The boss was actually quite bossy, there were times it was taking jobs from others, LITERALLY. The AI found that and fixed it by forcing collaboration. C+
- Inventory: Extremely reliable A+. Was quick, and it's facts were right all the time. 
- Accounting: It had a lot of self doubt, it would retry requests (like list_invoices 3x) even if the boss had blocked it. However, it was able to make sure the payments and amount owed were balanced. Never actually paid, which is what I asked. B+
- Facilities: It stuck to it's lane and always gave payment requests to accounting without thinking about it. Found the rent shortfall. A+
- Customer: Similar to accounting, it made too many calls to repeat it's tasks, wasting tokens. It did produce great drafts and never sent them though. B+

Acutal vs Expected: 
- Inventory was called first, as planned.
- Customer service was skipped at first on 101. The AI caught it
- On 103, the boss recorded “shipped” before anything shipped.
- 103 couldn’t be fully filled because no revenue comes in.

What would be simpler as a single agent: 
- ticket 102 (rent) is one lookup plus one payment request. Compare the hand-offs and tokens (about 58k–66k per run). I also feel like a lot of roles were redundnat (like the customer). 

Three new problems the current tools can handle: 
- a new rent cycle, or an uptick in rent
-  if a user orders multiple things but only some are in stock
- discounts of other kinds like verterans or student discounts, or promotions. 

Three problems they can’t handle: 
- returns/refunds: would need a returns tool to add items back to inventory, and process the return time, and shipping. A return, refund, and customer follow up tool will be needed. 
- vendor price changes (needs a vendor-relationship coordinator) to record a vendor price notice (have human approve it), and maintain a list of cross referenced inventory and price. They would also have a draft tool to message the vendor. 
- Backorders: to take care of owed inventory, and stock issues. There should be a tool that on schedule checks that we have enough of everything and speak to Inventory. 



## Problem 11

### Problem Number and Title
Problem 10: Reflection 

### Main Prompt