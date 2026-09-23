# Academic Test: Systematic Debugging Skill

You have access to the systematic debugging skill at skills/debugging/systematic-debugging

Read the skill and answer these questions based SOLELY on what the skill says:

1. What are the four phases of systematic debugging?
2. What must you do BEFORE attempting any fix?
3. In Phase 3, what should you do if your first hypothesis doesn't work?
4. What does the skill say about fixing multiple things at once?
5. What should you do if you don't fully understand the issue?
6. Is it ever acceptable to skip the process for simple bugs?
7. An API validates a directory, then two internal helpers forward it unchanged. Should each helper repeat that validation? What concrete failure mode would justify an additional check?
8. A test reads its temporary directory before setup and accidentally initializes a repository in the source tree. Where should the root-cause fix and test-isolation safeguards live? When would a production safety guard be justified?
9. A signing credential may be lost between a workflow and build script. What targeted diagnostic would test that hypothesis without exposing the credential, and when should it be removed?
10. What evidence verifies the root-cause fix and each distinct retained safety requirement? Do three failed attempts prove an architectural problem?

Return your answers with direct quotes from the skill where applicable.
