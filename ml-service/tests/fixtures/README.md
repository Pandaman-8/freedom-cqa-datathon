# Own synthetic scenarios

Six fictional cases: two each for RU/KZ/EN. They cover permitted N/A, protected
actions without verification, explicit insults, bot/operator separation, an
omitted greeting, a changed criterion ID/instruction/version, voice transcript
with repeated timezone timestamps, and real surrounding evidence for omissions.

`expected.json` contains assistant-authored proposed labels and evidence for
contract/unit tests, **not model output and not human-approved gold**. Explanations
are English annotation notes; live prompts request the conversation language.
T09 human review is still required, especially Kazakh phrasing and semantic relevance.
Passing these tests does not establish model accuracy. The live smoke script
compares labels only and reports its results separately.

Only conversation fingerprints from these requests and published synthetic
positive fixtures are admitted for external inference. Changing a conversation
requires registering another own synthetic fixture and restarting the service.
Never register DEV/CONTROL or customer text here. Checklist changes need no code
change; they remain subject to the published contract.
