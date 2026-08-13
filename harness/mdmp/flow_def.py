"""The MDMP flow: seven steps, from receipt of mission to a finished OPORD.

Every field carries a `plain` line written for someone who has never run MDMP,
and a `doctrine` line for someone who has. The `opord` list is what wires a
decision made in step 2 into paragraph 1c of the order in step 7 — that mapping
is the reason nobody has to retype anything at the end.
"""

from harness.flow import Field, Flow, Step

# ---------------------------------------------------------------------------
# Step 1 — Receipt of Mission
# ---------------------------------------------------------------------------

S1 = Step(
    key="receipt", num=1, title="Receipt of Mission", warnord=1,
    plain="You have just been given a job. Before anything else: who are you, "
          "what kind of fight is this, how long do you have, and who needs to "
          "know right now.",
    purpose="Alert the staff, allocate the available time, and issue initial "
            "guidance and the first warning order.",
    outputs=["Commander's initial guidance", "Time allocation", "WARNORD #1"],
    fields=[
        Field("unit_designation", "Your unit", kind="choice", gen="unit_designation",
              plain="The unit that will execute this order. Notional designations "
                    "are fine and are what training scenarios use.",
              doctrine="Appears in the heading of the order and as the subject "
                       "of the mission statement.",
              opord=["p2"], owner="s3",
              example="2d Brigade Combat Team, 52d Infantry Division"),

        Field("echelon", "Echelon", kind="choice", gen="echelon",
              plain="How big is the unit? This drives who your subordinates are "
                    "and how much detail the order needs.",
              doctrine="Echelon determines the two-up / one-up headquarters "
                       "referenced in paragraph 1d.",
              opord=[]),

        Field("operation_type", "Type of operation", kind="choice",
              gen="operation_type",
              plain="Offense, defense, stability, or defense support of civil "
                    "authorities — and the specific form.",
              doctrine="FM 3-0. Drives the forms of maneuver and the defensive "
                       "forms available in COA development.",
              opord=[]),

        Field("oe_framework", "Operational environment", kind="choice",
              gen="oe_framework",
              plain="Which training environment this scenario lives in. All "
                    "place and country names are notional.",
              doctrine="TC 7-101 / TC 7-102. Sets the threat template and the "
                       "terrain family used throughout.",
              opord=[]),

        Field("opfor_posture", "Threat posture", kind="choice", gen="opfor_posture",
              plain="How capable is the enemy? Peer, near-peer, hybrid, "
                    "irregular, or a mix.",
              doctrine="TC 7-100 series. Governs the threat capabilities that "
                       "may appear in the MLCOA and MDCOA.",
              opord=["p1c"], owner="s2"),

        Field("higher_two_up", "Higher headquarters, two levels up",
              kind="text", gen="higher_two_up",
              plain="The mission and intent of your boss's boss. You need it so "
                    "your plan nests inside theirs.",
              doctrine="FM 6-0, paragraph 1d(1). Mission, intent, and end state.",
              depends=["unit_designation", "echelon", "operation_type",
                       "oe_framework"],
              opord=["p1d"], owner="s3"),

        Field("higher_one_up", "Higher headquarters, one level up",
              kind="text", gen="higher_one_up",
              plain="Your immediate boss's mission, intent, and concept of "
                    "operations. This is the order you are responding to.",
              doctrine="FM 6-0, paragraph 1d(2). Includes the concept of "
                       "operations and your role in it.",
              depends=["unit_designation", "echelon", "operation_type",
                       "oe_framework", "higher_two_up"],
              opord=["p1d"], owner="s3"),

        Field("time_available", "Time allocation", kind="table",
              gen="time_available",
              columns=["Event", "When", "Who"],
              plain="Work backwards from execution. The old rule is one third "
                    "of the time for you, two thirds for subordinates.",
              doctrine="FM 5-0. The 1/3 – 2/3 rule; subordinates need time to "
                       "run their own troop leading procedures.",
              depends=["operation_type", "echelon"],
              opord=["p3h"], owner="xo"),

        Field("initial_guidance", "Commander's initial guidance", kind="text",
              gen="initial_guidance",
              plain="What the commander says in the first five minutes: how "
                    "much of the process to run, what to focus on, what to "
                    "start moving now.",
              doctrine="FM 5-0. Includes the initial time allocation, the "
                       "planning approach, and any movement to initiate.",
              depends=["operation_type", "echelon", "higher_one_up",
                       "time_available"],
              opord=[], owner="cdr"),
    ])


# ---------------------------------------------------------------------------
# Step 2 — Mission Analysis
# ---------------------------------------------------------------------------

S2 = Step(
    key="mission_analysis", num=2, title="Mission Analysis", warnord=2,
    plain="The long step, and the one that decides whether the rest is any "
          "good. Work out what you were told to do, what you must do that "
          "nobody said, what you know, what you are guessing, and what the "
          "enemy and the ground will do about it.",
    purpose="Understand the problem well enough to state the mission and issue "
            "planning guidance.",
    outputs=["Problem statement", "Mission statement", "Commander's intent",
             "Planning guidance", "CCIRs and EEFIs", "Assumptions",
             "Evaluation criteria", "WARNORD #2"],
    fields=[
        Field("area_of_interest", "Area of interest", kind="text",
              gen="area_of_interest",
              plain="The ground beyond your own area that you still care about "
                    "— because the enemy can reach you from it.",
              doctrine="Paragraph 1a. Includes the area from which the threat "
                       "can influence the operation.",
              depends=["oe_framework", "operation_type", "higher_one_up"],
              opord=["p1a"], owner="s2"),

        Field("terrain_effects", "Terrain effects (OAKOC)", kind="items",
              gen="terrain_effects", min_items=3,
              plain="Not a terrain description — a list of what the ground does "
                    "TO each side. 'The ridge blocks our observation' beats "
                    "'there is a ridge'.",
              doctrine="ATP 2-01.3. Observation and fields of fire, avenues of "
                       "approach, key terrain, obstacles, cover and concealment.",
              depends=["oe_framework", "operation_type", "area_of_interest"],
              opord=["p1b"], owner="s2"),

        Field("weather_effects", "Weather effects", kind="items",
              gen="weather_effects", min_items=2,
              plain="Same idea: what the weather does to flying, seeing, "
                    "moving, and shooting — for both sides.",
              doctrine="ATP 2-01.3. Visibility, wind, precipitation, cloud "
                       "cover, temperature and humidity, illumination.",
              depends=["oe_framework", "operation_type"],
              opord=["p1b"], owner="s2"),

        Field("enemy_composition", "Enemy composition, disposition, strength",
              kind="text", gen="enemy_composition",
              plain="Who the enemy is, where they are, and how much of them "
                    "there is.",
              doctrine="Paragraph 1c. Composition, disposition, strength, and "
                       "recent activities.",
              depends=["opfor_posture", "oe_framework", "echelon",
                       "operation_type"],
              opord=["p1c"], owner="s2"),

        Field("enemy_capabilities", "Enemy capabilities", kind="items",
              gen="enemy_capabilities", min_items=3,
              plain="What the enemy can actually do to you — fires, air "
                    "defense, drones, electronic warfare, information.",
              doctrine="TC 7-100 series. Capabilities must be consistent with "
                       "the task organization you gave the threat.",
              depends=["opfor_posture", "enemy_composition", "oe_framework"],
              opord=["p1c"], owner="s2"),

        Field("enemy_mlcoa", "Enemy most likely course of action", kind="text",
              gen="enemy_mlcoa",
              plain="What you expect the enemy to do. One paragraph, in the "
                    "same shape as your own concept: what, where, when, why.",
              doctrine="ATP 2-01.3. The MLCOA drives the friendly COA you plan "
                       "against by default.",
              depends=["enemy_composition", "enemy_capabilities",
                       "terrain_effects", "operation_type"],
              opord=["p1c"], owner="s2"),

        Field("enemy_mdcoa", "Enemy most dangerous course of action",
              kind="text", gen="enemy_mdcoa",
              plain="The one that hurts most if it happens. Not the least "
                    "likely — the most damaging one that is still possible.",
              doctrine="ATP 2-01.3. The MDCOA drives branch planning and much "
                       "of the risk discussion.",
              depends=["enemy_composition", "enemy_capabilities",
                       "terrain_effects", "operation_type"],
              opord=["p1c"], owner="s2"),

        Field("civil_considerations", "Civil considerations (ASCOPE)",
              kind="items", gen="civil_considerations", min_items=3,
              plain="The people and the built environment: who lives here, what "
                    "they need, what will make them help or hinder you.",
              doctrine="Areas, structures, capabilities, organizations, "
                       "people, events.",
              depends=["oe_framework", "operation_type", "area_of_interest"],
              opord=["p1f"], owner="s9"),

        Field("specified_tasks", "Specified tasks", kind="items",
              gen="specified_tasks", min_items=3,
              plain="Tasks the higher order tells you to do, in so many words. "
                    "Quote them.",
              doctrine="FM 5-0. Found in paragraphs 2, 3, and the coordinating "
                       "instructions of the higher order, and in its annexes.",
              depends=["higher_one_up", "operation_type", "echelon"],
              opord=[], owner="s3"),

        Field("implied_tasks", "Implied tasks", kind="items",
              gen="implied_tasks", min_items=3,
              plain="Tasks nobody stated but you must do anyway to accomplish "
                    "the mission. Routine, SOP-level tasks do not count.",
              doctrine="FM 5-0. Derived from the specified tasks, the enemy, "
                       "and the terrain.",
              depends=["specified_tasks", "terrain_effects", "enemy_mlcoa",
                       "operation_type"],
              opord=[], owner="s3"),

        Field("essential_tasks", "Essential tasks", kind="items",
              gen="essential_tasks", min_items=1,
              plain="The small set of tasks that must be done or the mission "
                    "fails. These go into the mission statement.",
              doctrine="FM 5-0. Essential tasks are specified or implied tasks "
                       "that must be executed to accomplish the mission.",
              depends=["specified_tasks", "implied_tasks", "higher_one_up"],
              opord=["p2"], owner="s3"),

        Field("constraints", "Constraints and restraints", kind="items",
              gen="constraints", min_items=2,
              plain="What you must do (constraint) and what you may not do "
                    "(restraint). Both come from higher.",
              doctrine="FM 5-0. Constraints require action; restraints prohibit "
                       "action.",
              depends=["higher_one_up", "specified_tasks"],
              opord=["p3h"], owner="s3"),

        Field("facts", "Critical facts", kind="items", gen="facts", min_items=3,
              plain="Things known to be true that matter to the plan. If you "
                    "cannot verify it, it is an assumption, not a fact.",
              doctrine="FM 5-0. Facts are statements of known data.",
              depends=["enemy_composition", "terrain_effects", "higher_one_up"],
              opord=[], owner="s3"),

        Field("assumptions", "Assumptions", kind="items", gen="assumptions",
              min_items=2,
              plain="Things you are treating as true so planning can continue. "
                    "Each one must be necessary, valid, and something you will "
                    "later confirm or deny.",
              doctrine="FM 5-0. An assumption replaces a necessary fact you do "
                       "not have. Too many assumptions is a symptom of an "
                       "under-developed plan.",
              depends=["facts", "enemy_mlcoa", "higher_one_up"],
              opord=["p1h"], owner="s3"),

        Field("shortfalls", "Resource shortfalls", kind="items", gen="shortfalls",
              min_items=1, required=False,
              plain="What you need and do not have. Say it now, in writing, "
                    "while higher can still fix it.",
              doctrine="FM 5-0. Compare available assets against the tasks; "
                       "request or accept risk.",
              depends=["essential_tasks", "echelon", "operation_type"],
              opord=[], owner="s4"),

        Field("problem_statement", "Problem statement", kind="text",
              gen="problem_statement",
              plain="One or two sentences naming the actual problem — the gap "
                    "between where you are and where you must be, and what is "
                    "in the way.",
              doctrine="ADP 5-0. The problem statement frames what the plan has "
                       "to solve.",
              depends=["essential_tasks", "enemy_mlcoa", "terrain_effects",
                       "constraints"],
              opord=[], owner="s3"),

        Field("mission_statement", "Restated mission statement", kind="text",
              gen="mission_statement",
              plain="One sentence: WHO does WHAT (task), WHEN, WHERE, and WHY "
                    "(purpose). This becomes paragraph 2 of the order.",
              doctrine="FM 5-0. Built from the essential tasks and the purpose "
                       "drawn from the higher commander's intent.",
              depends=["essential_tasks", "higher_one_up", "unit_designation",
                       "operation_type"],
              opord=["p2"], owner="cdr"),

        Field("intent_purpose", "Commander's intent — purpose", kind="text",
              gen="intent_purpose",
              plain="Why this operation matters in the larger fight. Broader "
                    "than the 'in order to' in the mission statement.",
              doctrine="ADP 5-0. Intent = expanded purpose + key tasks + end "
                       "state.",
              depends=["mission_statement", "higher_one_up"],
              opord=["p3a"], owner="cdr"),

        Field("intent_key_tasks", "Commander's intent — key tasks",
              kind="items", gen="intent_key_tasks", min_items=3,
              plain="What the force must do to succeed, stated so a subordinate "
                    "can act on it when the plan has fallen apart. Not a task "
                    "list for specific units.",
              doctrine="ADP 5-0. Key tasks are conditions the force must "
                       "achieve; they are not tied to a single COA.",
              depends=["mission_statement", "intent_purpose", "essential_tasks"],
              opord=["p3a"], owner="cdr"),

        Field("intent_end_state", "Commander's intent — end state", kind="text",
              gen="intent_end_state",
              plain="What 'done' looks like: friendly forces, enemy, terrain, "
                    "and civil situation at the end.",
              doctrine="ADP 5-0. Describe conditions, not actions.",
              depends=["mission_statement", "intent_purpose", "operation_type"],
              opord=["p3a"], owner="cdr"),

        Field("ccir_pir", "Priority intelligence requirements (PIR)",
              kind="items", gen="ccir_pir", min_items=2,
              plain="Questions about the enemy or the ground whose answers "
                    "would change a decision you are going to make.",
              doctrine="FM 6-0. A PIR ties to a decision point. If nothing "
                       "changes based on the answer, it is not a PIR.",
              depends=["enemy_mlcoa", "enemy_mdcoa", "mission_statement"],
              opord=["p3h"], owner="s2"),

        Field("ccir_ffir", "Friendly force information requirements (FFIR)",
              kind="items", gen="ccir_ffir", min_items=2,
              plain="Things about your own force that would change a decision "
                    "— combat power thresholds, class III/V status, key "
                    "capability loss.",
              doctrine="FM 6-0. CCIR = PIR + FFIR. The commander owns them.",
              depends=["mission_statement", "essential_tasks", "echelon"],
              opord=["p3h"], owner="s3"),

        Field("eefi", "Essential elements of friendly information (EEFI)",
              kind="items", gen="eefi", min_items=2,
              plain="What you must keep the enemy from finding out.",
              doctrine="FM 6-0. EEFIs are not CCIRs, but the staff manages "
                       "them with the same priority.",
              depends=["mission_statement", "intent_key_tasks"],
              opord=["p3h"], owner="s3"),

        Field("eval_criteria", "COA evaluation criteria", kind="multi",
              gen="eval_criteria", min_items=4,
              plain="How you will score the courses of action later. Choose "
                    "these NOW, before the COAs exist, so the comparison is "
                    "honest.",
              doctrine="FM 5-0. Criteria come from the commander's guidance and "
                       "the mission variables. Weight them in step 5.",
              depends=["mission_statement", "intent_purpose", "operation_type"],
              opord=[], owner="xo"),

        Field("planning_guidance", "Commander's planning guidance", kind="text",
              gen="planning_guidance",
              plain="What the commander wants the staff to do next: how many "
                    "COAs, what to consider, what to leave alone, how much risk "
                    "is acceptable.",
              doctrine="FM 5-0. Issued by warfighting function; drives COA "
                       "development directly.",
              depends=["mission_statement", "intent_purpose", "eval_criteria",
                       "assumptions"],
              opord=[], owner="cdr"),
    ])


# ---------------------------------------------------------------------------
# Step 3 — COA Development
# ---------------------------------------------------------------------------

S3 = Step(
    key="coa_development", num=3, title="COA Development",
    plain="Build genuinely different ways to do the job. Three plans that "
          "differ only in which company leads are one plan, not three.",
    purpose="Generate courses of action that are feasible, acceptable, "
            "suitable, distinguishable, and complete.",
    outputs=["COA statements", "COA sketches (described)", "Task organization"],
    fields=[
        Field("combat_power", "Relative combat power assessment", kind="text",
              gen="combat_power",
              plain="An honest look at strength against strength — not just a "
                    "bean count. Where are you stronger, where are they.",
              doctrine="FM 5-0. Compare by warfighting function, not by "
                       "vehicle count alone.",
              depends=["enemy_composition", "echelon", "operation_type"],
              opord=[], owner="s3"),

        Field("coa_1", "Course of action 1", kind="text", gen="coa_statement",
              plain="A full COA statement: the form of maneuver, the decisive "
                    "operation, the shaping operations, the main effort, and "
                    "the end state. Write it as a paragraph a subordinate could "
                    "act on.",
              doctrine="FM 5-0. Must answer what, when, where, how, and why, "
                       "and must pass the five screening criteria.",
              depends=["mission_statement", "intent_key_tasks", "enemy_mlcoa",
                       "terrain_effects", "combat_power", "operation_type",
                       "planning_guidance"],
              opord=[], owner="s3"),

        Field("coa_2", "Course of action 2", kind="text", gen="coa_statement",
              plain="A meaningfully different approach — different form of "
                    "maneuver, different decisive point, or different tempo.",
              doctrine="FM 5-0. Distinguishable: it must differ in a way that "
                       "changes the risk and the outcome.",
              depends=["mission_statement", "intent_key_tasks", "enemy_mlcoa",
                       "terrain_effects", "combat_power", "operation_type",
                       "coa_1"],
              opord=[], owner="s3"),

        Field("coa_3", "Course of action 3", kind="text", gen="coa_statement",
              required=False,
              plain="Optional third option. Two well-developed COAs beat three "
                    "thin ones.",
              doctrine="FM 5-0. The commander's guidance sets how many COAs to "
                       "develop.",
              depends=["mission_statement", "intent_key_tasks", "enemy_mlcoa",
                       "terrain_effects", "combat_power", "coa_1", "coa_2"],
              opord=[], owner="s3"),

        Field("coa_screening", "Screening check", kind="table",
              gen="coa_screening",
              columns=["COA", "Feasible", "Acceptable", "Suitable",
                       "Distinguishable", "Complete", "Note"],
              plain="Run each COA against the five gates before you spend a "
                    "war game on it.",
              doctrine="FM 5-0. A COA that fails any screen is fixed or "
                       "discarded, not carried forward.",
              depends=["coa_1", "coa_2", "coa_3"],
              opord=[], owner="xo"),

        Field("task_organization", "Task organization", kind="table",
              gen="task_organization",
              columns=["Unit", "Command relationship", "Role"],
              plain="Who works for whom for this operation, and what each is "
                    "there to do.",
              doctrine="FM 6-0. Command and support relationships: OPCON, "
                       "TACON, attached, DS, GS, GSR, R.",
              depends=["echelon", "unit_designation", "coa_1", "operation_type"],
              opord=["task_org"], owner="s3"),
    ])


# ---------------------------------------------------------------------------
# Step 4 — COA Analysis (War Game)
# ---------------------------------------------------------------------------

S4 = Step(
    key="coa_analysis", num=4, title="COA Analysis (War Game)",
    plain="Fight each plan against a thinking enemy, on paper. Action, "
          "reaction, counteraction. The point is to find what breaks while it "
          "is still cheap to fix.",
    purpose="Refine each COA, identify decision points, and build the "
            "synchronization matrix.",
    outputs=["War-game results", "Decision points", "Synchronization matrix",
             "Refined COAs"],
    fields=[
        Field("wargame_method", "War-game method", kind="choice",
              gen="wargame_method",
              plain="Belt, avenue-in-depth, or box. Pick by how the terrain and "
                    "the clock are shaped.",
              doctrine="FM 5-0. Belt for phased operations, avenue-in-depth for "
                       "offense along separate approaches, box when time is "
                       "short.",
              depends=["operation_type", "terrain_effects", "time_available"],
              opord=[], owner="s3"),

        Field("critical_events", "Critical events", kind="items",
              gen="critical_events", min_items=4,
              plain="The moments that decide the operation: crossing the line "
                    "of departure, a breach, commitment of the reserve, a "
                    "handover.",
              doctrine="FM 5-0. Critical events are war-gamed in sequence; each "
                       "produces decision points.",
              depends=["coa_1", "enemy_mlcoa", "operation_type"],
              opord=[], owner="s3"),

        Field("wargame_results", "War-game results", kind="table",
              gen="wargame_results",
              columns=["Event", "Friendly action", "Threat reaction",
                       "Friendly counteraction", "Finding"],
              plain="The actual action–reaction–counteraction record. The "
                    "'finding' column is the one that earns the step.",
              doctrine="FM 5-0. Record results as you go; they feed the "
                       "synchronization matrix and the COA refinements.",
              depends=["critical_events", "coa_1", "enemy_mlcoa", "enemy_mdcoa",
                       "wargame_method"],
              opord=[], owner="s3"),

        Field("decision_points", "Decision points", kind="table",
              gen="decision_points",
              columns=["#", "Decision", "Latest time / trigger", "Linked PIR"],
              plain="Points where the commander must decide something, with the "
                    "information that triggers the decision and the last moment "
                    "it can be made.",
              doctrine="FM 6-0. Every decision point should tie to a PIR and to "
                       "a named area of interest.",
              depends=["wargame_results", "ccir_pir", "critical_events"],
              opord=["p3h"], owner="s3"),

        Field("sync_matrix", "Synchronization matrix", kind="table",
              gen="sync_matrix",
              columns=["Phase / time", "Movement and Maneuver", "Intelligence",
                       "Fires", "Sustainment", "Protection", "Command and Control"],
              plain="Time across the top, warfighting functions down the side. "
                    "This is what turns a concept into something executable.",
              doctrine="FM 5-0. The synchronization matrix is the primary "
                       "war-game record and the basis of the execution matrix.",
              depends=["wargame_results", "critical_events", "coa_1"],
              opord=["p3b"], owner="s3"),

        Field("risk_register", "Risk assessment", kind="table",
              gen="risk_register",
              columns=["Hazard", "Probability", "Severity", "Level", "Control",
                       "Residual"],
              plain="Hazards, how likely and how bad, what you will do about "
                    "each, and what risk is left after the control.",
              doctrine="ATP 5-19. Identify, assess, develop controls, "
                       "implement, supervise. Probability × severity gives the "
                       "level.",
              depends=["wargame_results", "enemy_mdcoa", "operation_type"],
              opord=["p3h"], owner="s3"),
    ])


# ---------------------------------------------------------------------------
# Step 5 — COA Comparison
# ---------------------------------------------------------------------------

S5 = Step(
    key="coa_comparison", num=5, title="COA Comparison",
    plain="Score the plans against the criteria you set in step 2, then say "
          "out loud what each one costs.",
    purpose="Identify the COA with the highest probability of success and "
            "produce a staff recommendation.",
    outputs=["Decision matrix", "Advantages and disadvantages",
             "Staff recommendation"],
    fields=[
        Field("criteria_weights", "Criteria weights", kind="table",
              gen="criteria_weights",
              columns=["Criterion", "Weight", "Why this weight"],
              plain="Not every criterion matters equally. Weight them before "
                    "you score, and write down why.",
              doctrine="FM 5-0. Weighting is a command decision informed by the "
                       "planning guidance.",
              depends=["eval_criteria", "planning_guidance"],
              opord=[], owner="xo"),

        Field("decision_matrix", "Decision matrix", kind="table",
              gen="decision_matrix",
              columns=["Criterion", "Weight", "COA 1", "COA 2", "COA 3"],
              plain="Score each COA against each criterion. Lower total wins if "
                    "you rank 1 = best; state your convention and keep it.",
              doctrine="FM 5-0. The matrix informs the recommendation; it does "
                       "not make the decision.",
              depends=["criteria_weights", "coa_1", "coa_2", "coa_3",
                       "wargame_results"],
              opord=[], owner="xo"),

        Field("coa_advantages", "Advantages and disadvantages", kind="table",
              gen="coa_advantages",
              columns=["COA", "Advantages", "Disadvantages", "Risk"],
              plain="The part the commander actually reads. Be blunt.",
              doctrine="FM 5-0. Pair every advantage with what it costs.",
              depends=["decision_matrix", "coa_1", "coa_2", "coa_3",
                       "risk_register"],
              opord=[], owner="xo"),

        Field("staff_recommendation", "Staff recommendation", kind="text",
              gen="staff_recommendation",
              plain="Which COA the staff recommends and why, in a paragraph.",
              doctrine="FM 5-0. State the recommendation, the decisive reason, "
                       "and the risk the commander is accepting.",
              depends=["decision_matrix", "coa_advantages"],
              opord=[], owner="xo"),
    ])


# ---------------------------------------------------------------------------
# Step 6 — COA Approval
# ---------------------------------------------------------------------------

S6 = Step(
    key="coa_approval", num=6, title="COA Approval", warnord=3,
    plain="The commander picks one, sharpens the intent, and says what they "
          "still need to know. Then the third warning order goes out.",
    purpose="Obtain the commander's decision, refined intent, and final "
            "planning guidance.",
    outputs=["Approved COA", "Refined intent", "Refined CCIRs", "WARNORD #3"],
    fields=[
        Field("approved_coa", "Approved course of action", kind="choice",
              gen="approved_coa",
              plain="Which COA is approved — including a modified one, which is "
                    "the most common outcome.",
              doctrine="FM 5-0. The commander may approve, modify, or direct a "
                       "new COA.",
              depends=["staff_recommendation", "coa_1", "coa_2", "coa_3"],
              opord=["p3b"], owner="cdr"),

        Field("coa_modifications", "Modifications directed", kind="items",
              gen="coa_modifications", required=False, min_items=0,
              plain="What the commander changed about the COA on approval.",
              doctrine="FM 5-0. Modifications are captured before orders "
                       "production begins, not during it.",
              depends=["approved_coa", "coa_advantages"],
              opord=["p3b"], owner="cdr"),

        Field("final_guidance", "Final planning guidance", kind="text",
              gen="final_guidance",
              plain="Last direction before the order is written: priorities, "
                    "risk accepted, rehearsal intent, timeline.",
              doctrine="FM 5-0. Includes refined CCIRs and any changes to the "
                       "acceptable level of risk.",
              depends=["approved_coa", "coa_modifications", "risk_register"],
              opord=["p3h"], owner="cdr"),

        Field("rehearsals", "Rehearsal plan", kind="items", gen="rehearsals",
              min_items=2,
              plain="Which rehearsals, when, who attends, and to what standard.",
              doctrine="FM 6-0. Types include confirmation brief, backbrief, "
                       "combined arms rehearsal, and support rehearsal.",
              depends=["approved_coa", "time_available", "echelon"],
              opord=["p3h"], owner="s3"),
    ])


# ---------------------------------------------------------------------------
# Step 7 — Orders Production
# ---------------------------------------------------------------------------

S7 = Step(
    key="orders_production", num=7,
    title="Orders Production, Dissemination, and Transition",
    plain="Turn the approved plan into a five-paragraph order. Most of it is "
          "already written — everything you decided in steps 1 through 6 is "
          "waiting in the draft. Fill the gaps, assign the paragraphs, and "
          "publish.",
    purpose="Produce, disseminate, and transition the OPORD.",
    outputs=["OPORD", "Annexes", "Confirmation briefs"],
    fields=[
        Field("references", "References", kind="items", gen="references",
              min_items=2,
              plain="Maps and documents someone needs in hand to understand the "
                    "order.",
              doctrine="FM 6-0. Map series, sheet name and number, edition, "
                       "scale, and the higher order being executed.",
              depends=["oe_framework", "higher_one_up"],
              opord=["references"], owner="s3"),

            Field("time_zone", "Time zone used throughout the order",
              kind="choice", gen="time_zone",
              plain="One time zone for the entire order and every annex.",
              doctrine="FM 6-0. Stated once, immediately after the references.",
              depends=["oe_framework"],
              opord=["time_zone"], owner="s3"),

        Field("concept_of_operations", "Concept of operations", kind="text",
              gen="concept_of_operations",
              plain="The heart of paragraph 3: decisive operation, shaping "
                    "operations, sustaining operations, main effort, by phase.",
              doctrine="FM 6-0, paragraph 3b. Must be consistent with the "
                       "approved COA and the synchronization matrix.",
              depends=["approved_coa", "coa_modifications", "sync_matrix",
                       "intent_end_state"],
              opord=["p3b"], owner="s3"),

        Field("tasks_to_subordinates", "Tasks to subordinate units",
              kind="table", gen="tasks_to_subordinates",
              columns=["Unit", "Task", "Purpose", "Priority"],
              plain="One line per subordinate: a doctrinal task verb and the "
                    "purpose it serves.",
              doctrine="FM 6-0, paragraph 3g. Listed in task-organization "
                       "order. Every essential task must appear against some "
                       "unit.",
              depends=["approved_coa", "task_organization", "essential_tasks",
                       "sync_matrix"],
              opord=["p3g"], owner="s3"),

        Field("scheme_maneuver", "Scheme of movement and maneuver", kind="text",
              gen="scheme_maneuver",
              plain="How the maneuver force actually moves and fights, phase by "
                    "phase.",
              doctrine="FM 6-0, paragraph 3c.",
              depends=["concept_of_operations", "approved_coa", "sync_matrix"],
              opord=["p3c"], owner="s3"),

        Field("scheme_intelligence", "Scheme of intelligence and collection",
              kind="text", gen="scheme_intelligence",
              plain="How you will answer the PIRs: who collects, where, when, "
                    "and what they report to whom.",
              doctrine="FM 6-0, paragraph 3d. Ties collection assets to named "
                       "areas of interest and decision points.",
              depends=["ccir_pir", "decision_points", "enemy_mlcoa",
                       "concept_of_operations"],
              opord=["p3d"], owner="s2"),

        Field("scheme_fires", "Scheme of fires", kind="text", gen="scheme_fires",
              plain="Priority of fires, fire support tasks, and how fires "
                    "enable the decisive operation.",
              doctrine="FM 6-0, paragraph 3e. Include fire support coordination "
                       "measures and the target list reference.",
              depends=["concept_of_operations", "approved_coa", "sync_matrix"],
              opord=["p3e"], owner="fso"),

        Field("scheme_protection", "Scheme of protection", kind="text",
              gen="scheme_protection",
              plain="Survivability, air and missile defense, CBRN, personnel "
                    "recovery, and safety.",
              doctrine="FM 6-0, paragraph 3f.",
              depends=["concept_of_operations", "risk_register",
                       "enemy_capabilities"],
              opord=["p3f"], owner="eng"),

        Field("sustainment_concept", "Concept of support", kind="text",
              gen="sustainment_concept",
              plain="How the operation is fed, fuelled, armed, fixed, and "
                    "medically covered. If support cannot carry the concept, "
                    "the plan is not feasible.",
              doctrine="FM 6-0, paragraph 4. Logistics, personnel, and health "
                       "service support.",
              depends=["concept_of_operations", "task_organization",
                       "shortfalls", "echelon"],
              opord=["p4"], owner="s4"),

        Field("command_posts", "Command post locations and reports",
              kind="text", gen="command_posts",
              plain="Where the command posts are, when they move, and what "
                    "reports are due when.",
              doctrine="FM 6-0, paragraph 5b.",
              depends=["concept_of_operations", "echelon"],
              opord=["p5b"], owner="s3"),

        Field("succession", "Succession of command", kind="text",
              gen="succession",
              plain="Who takes over, in order, if the commander is out.",
              doctrine="FM 6-0, paragraph 5a.",
              depends=["task_organization", "echelon"],
              opord=["p5a"], owner="s3"),

        Field("pace_plan", "PACE plan", kind="table", gen="pace_plan",
              columns=["Net / user", "Primary", "Alternate", "Contingency",
                       "Emergency"],
              plain="Primary, alternate, contingency, emergency — for each net "
                    "or user group. Everyone must know when to jump.",
              doctrine="FM 6-0, paragraph 5c. Include the trigger for moving "
                       "from one means to the next.",
              depends=["concept_of_operations", "echelon", "task_organization"],
              opord=["p5c"], owner="s6"),
    ])


FLOW = Flow(
    flow_id="mdmp_opord",
    title="MDMP → OPORD",
    description=(
        "Seven steps of the military decision-making process, ending in a "
        "five-paragraph operation order. Every decision you make is carried "
        "forward into the order automatically."
    ),
    steps=[S1, S2, S3, S4, S5, S6, S7],
)
