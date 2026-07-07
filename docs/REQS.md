I want to make a simple kanban app. For now, it should just be an MVP (priotritize shipping something deployable).

What it is - a simple Kanban app that software engineers and other teams can use. It should be a CRUD app with frontend, backend, and persistent database

Who it's for - primarily teams that use scrum / kanban like software engineering teams

Why - I want a simple kanban app that can be extensible and include future integration with an MCP server and CLI so that LLM agents can execute actions on the kanban app

Rough features
- Ability to have todo, in progress, and done columns
- In the frontend, ability to move cards between columns
- Cards should have title, description, story points, assigned to, etc. (help me plan this out for the MVP)
- Each Kanban card should also have a number (something similar to a Jira ticket number)
- There should be an API as well so external parties (users, LLMs, MCP, CLI) can hit an API and perform actions in the kanban app.


Constraints / preferences
- Primarily for the MVP there should be a UI that i can interact with and demo to users
- Frontend uses Svelte (choose Svelte 5 and Vite 8)
- Backend uses FastAPI
- Database use SQLite (for now but may consider using postgres in the future)
- Do not include any authentication or billing features. Just a simple app with no auth for now
- Github actions to do CI/CD so that I can deploy this app somewhere so that other people can use it (give me recommendations and tell me how to do this for free / low cost. I have tried to deploy on digitalocean in the past.)