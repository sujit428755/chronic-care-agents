"""85 extra synthetic articles (neutral program information, never medical advice).
Tuple: (id, title, program, scope, type, status, body)."""
A = "All programs"
D, H, C = "Diabetes Support", "Hypertension Support", "Cardiac Wellness"

def _bul(*xs): return "\n".join(f"- {x}" for x in xs)

EDU = [
 ("Using the Reminder Settings", A, "How-to", "Reminders reach you through the channel saved in your profile (App, SMS or Email).\n\n## What you can expect\n" + _bul("One reminder per due task.", "Reminders name the task and its due date only.", "Program staff change the channel for you.")),
 ("What Your Member ID Is For", A, "Program basics", "Your member ID identifies your record in the program. Staff may ask for it when you call.\n\n" + _bul("Keep it handy when contacting the program.", "Do not share it in public messages.", "In the activity log it is partly hidden.")),
 ("How a Care Call Is Scheduled", A, "Process", "Care calls are booked by program staff. You receive the date and time through your preferred channel.\n\n" + _bul("Calls are listed as tasks in your care plan.", "To change a time, contact program staff.")),
 ("Reading Your Weekly Summary", A, "How-to", "A weekly summary lists the entries you recorded, in date order, with the dates that have no entry.\n\n" + _bul("It reports only what you entered.", "It does not explain what numbers mean.", "Questions about meaning go to your clinician.")),
 ("What Happens After You Save an Entry", A, "Process", "When you save an entry it is stored with its date and time. It appears in your next summary.\n\n" + _bul("Corrections replace the old entry.", "The old entry is kept only for the audit trail.")),
 ("Understanding Task Frequencies", A, "Care plan basics", "A task repeats Daily, Weekly or Monthly, or happens Once.\n\n" + _bul("Daily: every day.", "Weekly: once a week.", "Monthly: once a month.", "Once: a single task.")),
 ("What Overdue Means", A, "Care plan basics", "Overdue means the due date has passed and the task is not marked completed. The status is shown exactly as recorded by your care team."),
 ("What Scheduled Means", A, "Care plan basics", "Scheduled means the task has a planned date in the future, for example a coordinator check-in."),
 ("How to Prepare for a Coordinator Check-in", A, "Checklist", "A coordinator check-in is an administrative call about your program.\n\n" + _bul("Have your recent entries ready.", "Note any questions about the program.", "Questions about treatment are for your clinician.")),
 ("Keeping a Simple Entry Habit", A, "Habit support", "Many members link their entry to a daily moment, such as after breakfast. A fixed moment makes entries easier to remember. The choice of time is yours."),
 ("Using the App on a Shared Device", A, "Privacy basics", "If you share a device, sign out after use so others cannot see your entries.\n\n" + _bul("Sign out when finished.", "Do not save your password on shared devices.")),
 ("Language Options in the Program", A, "Program basics", "Messages can be sent in the language saved in your profile. Program staff update it on request."),
 ("Understanding Consent in the Program", A, "Privacy basics", "Consent means you agree to the program using your information for follow-up.\n\n" + _bul("Active: the program can help you.", "Expired, Pending or Revoked: the program stops and staff contact you.")),
 ("How to Renew Your Consent", A, "Process", "When your consent has expired, program staff help you renew it. The program cannot process requests until it is active again."),
 ("What the Activity Log Records", A, "Privacy basics", "The activity log records which steps ran and which rules applied. It does not store your messages or your entry values. Member IDs are partly hidden."),
 ("How Staff Review Requests Work", A, "Process", "When a request needs a person, it is placed in a staff review list with the facts and no interpretation. Staff follow up through your preferred channel."),
 ("Understanding Entry Dates and Times", A, "How-to", "Each entry has a date and time. Check them before you save. If the time is wrong, enter a corrected entry and tell program staff."),
 ("Why Some Dates Show No Entry", A, "How-to", "A date with no entry is simply listed as missing. Nothing is filled in or estimated for you."),
 ("Getting Started with Diabetes Support", D, "Program orientation", "Welcome to Diabetes Support. The program helps you stay in touch with your care team.\n\n" + _bul("Reminders for your care plan tasks.", "A place to record glucose entries.", "Staff follow-up when a person needs to look at something.")),
 ("Getting Started with Cardiac Wellness", C, "Program orientation", "Welcome to Cardiac Wellness. The program organises your entries and tasks for your care team.\n\n" + _bul("Reminders for your tasks.", "A place to record blood pressure and weight entries.", "Staff follow-up when needed.")),
 ("Recording Glucose Entries in the App", D, "How-to", "Choose Glucose, type the number as your device shows it, check the date and time, then save."),
 ("Recording Blood Pressure Entries in the App", H, "How-to", "Choose Blood pressure and type both numbers in the form 128/82, then check the date and time and save."),
 ("Recording Weight Entries in the App", C, "How-to", "Choose Weight, type the number in kilograms, check the date and time, then save."),
 ("Using the Same Device Each Time", A, "Habit support", "Using the same home device for your entries keeps them consistent. Your clinician decides how to use them."),
 ("Writing Down Questions for Your Clinician", A, "Checklist", "Keep a running list of questions in the app notes or on paper. Bring it to your clinic visit."),
 ("What the Program Cannot Do", A, "Program basics", "The program organises information. It does not diagnose, give medical advice or change medicines. Those are for your clinician."),
 ("Who to Contact for What", A, "Program basics", _bul("Program questions: program staff.", "Treatment questions: your clinician.", "Emergencies: local emergency services.")),
 ("Understanding Staff Follow-up", A, "Process", "Staff follow-up means a person from the program contacts you. It is a routine step and not an interpretation of your entries."),
 ("How Education Articles Are Approved", A, "Program basics", "Only articles approved by the program content lead are shown. Each has an ID and a version number. Draft and retired articles are not used."),
 ("Understanding Article Versions", A, "Program basics", "Articles are numbered v1, v2 and so on. The version shown with an answer is the approved version at that time."),
 ("Using the Member Assistant", A, "How-to", "You can ask for a summary of your entries, a list of your tasks, or approved program information. For anything else the assistant asks staff to follow up."),
 ("Typing Dates in Your Messages", A, "How-to", "You can write 'last 7 days', 'last 14 days' or 'this month'. If you give no period, a default period is used."),
 ("Changing Your Preferred Channel", A, "How-to", "Ask program staff to change your channel between App, SMS and Email. The change applies to future reminders."),
 ("What to Do If You Cannot Sign In", A, "How-to", "Contact program staff. They can help with access. Do not share your password in messages."),
 ("Taking Part Through a Family Member", A, "Privacy basics", "If a family member helps with the app, the program still uses only your consent. Ask program staff about adding a helper."),
 ("Respecting Quiet Hours", A, "Reminders", "Reminders are sent at the times set in your profile. Ask program staff to adjust them."),
 ("Understanding Program Messages", A, "Reminders", "Program messages are reminders and administrative notices. They never contain advice about treatment."),
 ("Using Notes on Entries", A, "How-to", "You may add a short note to an entry, for example 'before breakfast'. Notes are stored as typed and are not interpreted."),
 ("How Long Your Information Is Kept", A, "Privacy basics", "Retention periods are set by the program. For the exact period ask program staff. (Synthetic content.)"),
 ("Moving to a Different Program", A, "Process", "If your care team moves you to another program, staff update your profile. Your earlier entries stay in your record."),
 ("Taking a Break from the Program", A, "Process", "To pause, tell program staff. They update your consent and reminders as agreed with you."),
]
FAQ = [
 ("How do I see my care plan tasks?", "Ask the assistant to list your tasks. They are shown as recorded with their due dates and statuses."),
 ("Why did I get a reminder?", "A reminder is sent when a task in your care plan is due or overdue."),
 ("Can I change a due date?", "Due dates are set by your care team. Contact program staff to ask for a change."),
 ("How do I mark a task completed?", "Tell program staff or use the task option in the app if available. The status is recorded by your care team."),
 ("What does Open mean?", "Open means the task is in your plan and not yet due."),
 ("What does Completed mean?", "Completed means the task has been marked as done in your care plan."),
 ("Who writes the program articles?", "Articles are prepared and approved by the program content team (synthetic content)."),
 ("Why did the assistant not answer my question?", "If no approved article covers it, the assistant asks program staff to follow up instead of guessing."),
 ("Why was my request sent to staff?", "Some requests need a person. The assistant passes the facts to staff without interpreting them."),
 ("Does the assistant read my messages aloud to others?", "No. Staff see a summary packet only when follow-up is needed."),
 ("How are my entries protected?", "Entries are used only with active consent, and the activity log stores no entry values."),
 ("What if my consent has expired?", "The program stops processing. Contact program staff to renew it."),
 ("Can I withdraw my consent?", "Yes. Tell program staff. They update your profile."),
 ("How do I update my phone number?", "Contact program staff. They change the number in your profile."),
 ("How do I update my email address?", "Contact program staff. They change the email in your profile."),
 ("Can I get reminders in two channels?", "A profile has one preferred channel. Ask program staff if other options exist."),
 ("Can I use the program without the app?", "Yes. SMS and Email channels are available through program staff."),
 ("What period does a summary cover?", "The period you ask for, for example the last 7 days. Without one, a default period is used."),
 ("Why does my summary list missing dates?", "Dates with no entry are listed as missing. Nothing is estimated."),
 ("What if I entered the wrong time?", "Enter a corrected entry and tell program staff. The old entry is marked as replaced."),
 ("Can staff see my old corrected entries?", "Staff can see that a correction happened. Summaries use only the corrected entry."),
 ("What is a staff review?", "A person from the program looks at the facts passed on and contacts you if needed."),
 ("How long does a staff follow-up take?", "Times are set by the program. Ask program staff for the current timing."),
 ("Can the assistant book appointments?", "No. Program staff book calls and appointments."),
 ("Does the assistant know my medicines?", "No. It does not hold or discuss medicines. Ask your clinician."),
 ("Who do I ask about my treatment?", "Your clinician. The program does not give treatment advice."),
 ("Is the assistant a doctor?", "No. It organises information and hands requests to people."),
 ("What languages are supported?", "The languages saved in the member profiles, for example English, Hindi, Kannada, Tamil, Telugu and Marathi."),
 ("Why does the assistant add a disclaimer?", "To remind you that it organises information and is not a clinician."),
 ("What is an article ID?", "A short code such as EDU-401 that names the approved article an answer came from."),
]
CPG = [
 ("Handling a task with an unusual frequency", "Report the frequency as recorded. If it is not one of Daily, Weekly, Monthly or Once, ask staff to review the care plan record."),
 ("Reporting statuses exactly as recorded", "The system never recalculates a status. A task shown as Due is reported as Due even if the date has passed."),
 ("Grouping tasks in a reminder", "List each due task with its name, due date and recorded status. Keep the wording neutral."),
 ("Reminders for overdue tasks", "Use a polite, neutral tone. Name the task and date. Never mention values, interpretations or advice."),
 ("Reminder language", "Write the reminder in the language saved in the member profile when supported; otherwise use English and tell staff."),
 ("Check-in questions", "A check-in question asks whether the member needs help with the program, never about symptoms or treatment."),
 ("When a care plan has no tasks", "Report that no tasks are recorded and offer a staff follow-up. Do not invent tasks."),
 ("Completed tasks in summaries", "List completed tasks only if asked. Completed tasks are not turned into reminders."),
 ("Tasks for members without consent", "Do not read the care plan. Direct the member to program staff (rule ER-501)."),
 ("Duplicate tasks", "If two tasks share a name and date, report both as recorded and ask staff to review the care plan."),
 ("Tasks due today", "A task due today is reported with its recorded status, whatever that is."),
 ("Coordinator check-in tasks", "Coordinator check-ins are program contacts, not clinical visits. Describe them neutrally."),
 ("Education module tasks", "An education module task names the module. Do not summarise clinical content in the reminder."),
 ("Staff queue notes", "A staff note states the rule IDs, record IDs and period, and says no interpretation was made."),
 ("Closing a staff review item", "Staff record who reviewed the item and add a short note. The member message is not changed by the system."),
]
ADD_STATUS = {  # per-type index (0-based) -> status, to give the catalog some Draft/Retired rows
    ("edu", 36): "Draft", ("edu", 37): "Draft", ("faq", 27): "Retired", ("faq", 28): "Draft", ("cpg", 13): "Retired", ("cpg", 14): "Draft", ("edu", 30): "Retired",
}

def build():
    out = []
    for i, (t, p, sc, b) in enumerate(EDU):
        out.append((f"EDU-{411 + i}", t, p, sc, "education", ADD_STATUS.get(("edu", i), "Approved"), b))
    for i, (q, a) in enumerate(FAQ):
        out.append((f"FAQ-{709 + i}", q, A, "Program FAQ", "faq", ADD_STATUS.get(("faq", i), "Approved"), a))
    for i, (t, b) in enumerate(CPG):
        out.append((f"CPG-{807 + i}", t, A, "Care plan guidance", "careplan_guidance", ADD_STATUS.get(("cpg", i), "Approved"), b))
    return out
