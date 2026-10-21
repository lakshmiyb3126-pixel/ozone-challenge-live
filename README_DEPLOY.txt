OZONE CHALLENGE — PRIVATE TEACHER LEADERBOARD (12 QUESTIONS)
================================================================

WHAT CHANGED
- Students can access the public quiz at your Render site's home URL.
- Students see only their own result; class scores are no longer shown on phones.
- Teacher views the entire class leaderboard separately at /teacher.
- /teacher shows a password login page unless already signed in.
- /api/board is also protected by a server-side login cookie (not just hidden HTML).
- Refresh updates counts and ranks immediately; automatic refresh every 2 seconds.
- Reset scores requires a teacher login AND the password again.

UPDATE YOUR EXISTING GITHUB REPOSITORY (NO NEW REPO NEEDED)
1. Open your GitHub repository ozone-challenge-live > Code > Add file > Upload files.
2. From THIS ZIP upload all FIVE application files (replace existing matching ones):
   index.html, teacher.html, teacher_login.html, ozone_server.py, render.yaml
3. Commit changes on main.
4. Open Render Dashboard > ozone-challenge-quiz service > Environment.
5. Add environment variable:
       KEY:   OZONE_TEACHER_PASSWORD
       VALUE: (YOUR OWN STRONG PRIVATE PASSWORD, at least 12 characters)
   Do NOT use an example password. Do NOT upload the password into GitHub.
6. Save/Deploy if requested. Check Events/Logs for successful deployment, status Live.
   Render usually redeploys automatically when code changes on connected GitHub.

STUDENT AND TEACHER LINKS
Students: https://YOUR-RENDER-DOMAIN.onrender.com/
Teacher:  https://YOUR-RENDER-DOMAIN.onrender.com/teacher
Keep teacher password confidential. Teacher URL itself is not a secret.

IMPORTANT
- If you receive a 503 on teacher login, set OZONE_TEACHER_PASSWORD on Render.
- If Refresh gives a login error, sign in again at /teacher.
- Free Render instances use ephemeral SQLite disk: scores may reset on redeploy/restart.
- A Render deployment typically replaces the current instance; finish tests and reset
  the scores before you run the actual class quiz.
- Do not share your teacher password or cookie with students.
- The files and source code in a public GitHub repository remain visible, but the
  password is never embedded in source code, and score retrieval is authenticated.
- This is a small-classroom solution, not a hardened production authentication service.
