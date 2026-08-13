"""Doctrinal reference data for the MDMP flow.

This module is the knowledge core of the harness. Everything the offline
generators produce, and everything the OPORD renderer assembles, is built from
the structures here. It is deliberately plain Python data so that a staff
officer can read it, correct it, and extend it without touching the engine.

Primary references (see corpus/README.md for the publication list):
  FM 5-0   Planning and Orders Production
  ADP 5-0  The Operations Process
  FM 6-0   Commander and Staff Organization and Operations
  FM 3-0   Operations
  ATP 2-01.3 Intelligence Preparation of the Battlefield
  ATP 5-19 Risk Management
  TC 7-100 series  Opposing Force doctrine
  TC 7-101 Exercise Design
"""

# --------------------------------------------------------------------------
# The seven steps of MDMP
# --------------------------------------------------------------------------

MDMP_STEPS = [
    {
        "num": 1,
        "key": "receipt",
        "title": "Receipt of Mission",
        "plain": "You just got told you have a job to do. Figure out how much "
                 "time you have, wake the staff up, and send a heads-up down.",
        "purpose": "Alert the staff, allocate available time, and issue the "
                   "commander's initial guidance and the first warning order.",
        "outputs": ["Commander's initial guidance", "Initial time allocation",
                    "WARNORD #1"],
    },
    {
        "num": 2,
        "key": "mission_analysis",
        "title": "Mission Analysis",
        "plain": "Work out what you were actually told to do, what you must do "
                 "that nobody said out loud, what you know, what you're guessing, "
                 "and what the enemy and the terrain are going to do about it.",
        "purpose": "Understand the problem and the operational environment well "
                   "enough to state the mission and issue planning guidance.",
        "outputs": ["Problem statement", "Restated mission statement",
                    "Initial commander's intent", "Initial planning guidance",
                    "Initial CCIRs and EEFIs", "Updated IPB products",
                    "Assumptions", "COA evaluation criteria", "WARNORD #2"],
    },
    {
        "num": 3,
        "key": "coa_development",
        "title": "COA Development",
        "plain": "Come up with genuinely different ways to accomplish the "
                 "mission — not one plan with three paint jobs.",
        "purpose": "Generate options that are feasible, acceptable, suitable, "
                   "distinguishable, and complete.",
        "outputs": ["COA statements and sketches", "Task organization by COA",
                    "Updated running estimates"],
    },
    {
        "num": 4,
        "key": "coa_analysis",
        "title": "COA Analysis (War Game)",
        "plain": "Fight each plan against a thinking enemy on paper. Action, "
                 "reaction, counteraction. Write down what breaks.",
        "purpose": "Refine each COA, identify decision points, and produce the "
                   "synchronization matrix.",
        "outputs": ["War-game results", "Decision points",
                    "Refined COAs", "Synchronization matrix", "Refined CCIRs"],
    },
    {
        "num": 5,
        "key": "coa_comparison",
        "title": "COA Comparison",
        "plain": "Score the plans against the criteria you set earlier, and be "
                 "honest about the trade-offs.",
        "purpose": "Identify the COA with the highest probability of success "
                   "against the criteria the commander cares about.",
        "outputs": ["Decision matrix", "Advantages and disadvantages",
                    "Staff recommendation"],
    },
    {
        "num": 6,
        "key": "coa_approval",
        "title": "COA Approval",
        "plain": "The commander picks one, refines the intent, and says what "
                 "they still need to know.",
        "purpose": "Obtain the commander's decision, refined intent, and final "
                   "planning guidance.",
        "outputs": ["Approved COA", "Refined commander's intent",
                    "Refined CCIRs and EEFIs", "WARNORD #3"],
    },
    {
        "num": 7,
        "key": "orders_production",
        "title": "Orders Production, Dissemination, and Transition",
        "plain": "Turn the approved plan into a five-paragraph order people can "
                 "actually execute, then hand it over.",
        "purpose": "Produce, disseminate, and transition the OPORD.",
        "outputs": ["OPORD", "Annexes", "Confirmation briefs", "Rehearsals"],
    },
]

STEP_BY_KEY = {s["key"]: s for s in MDMP_STEPS}


# --------------------------------------------------------------------------
# Variables and frameworks
# --------------------------------------------------------------------------

# Operational variables (used to describe the operational environment)
PMESII_PT = [
    ("political", "Political",
     "Governance, legitimacy, factions, host-nation authority, coalition politics."),
    ("military", "Military",
     "Force composition, disposition, capability, readiness, and posture — "
     "friendly, threat, and third-party."),
    ("economic", "Economic",
     "Resource flows, industry, markets, black economy, employment, funding of "
     "the threat."),
    ("social", "Social",
     "Population, ethnic and tribal structure, religion, grievances, migration."),
    ("information", "Information",
     "Media, narrative, connectivity, information operations, public perception."),
    ("infrastructure", "Infrastructure",
     "Power, water, transportation, medical, communications, ports, and "
     "airfields."),
    ("physical_environment", "Physical Environment",
     "Terrain, weather, hydrography, urban density, and their effect on both "
     "forces."),
    ("time", "Time",
     "Tempo, planning horizons, cultural perception of time, decision windows."),
]

# Mission variables. FM 3-0 (2022) adds informational considerations: METT-TC (I)
METT_TC_I = [
    ("mission", "Mission", "The task and purpose — what and why."),
    ("enemy", "Enemy", "Composition, disposition, strength, and likely actions."),
    ("terrain", "Terrain and Weather",
     "OAKOC: observation and fields of fire, avenues of approach, key terrain, "
     "obstacles, cover and concealment."),
    ("troops", "Troops and Support Available",
     "Your own units, attachments, and the resources you actually control."),
    ("time_available", "Time Available",
     "Time to plan, prepare, and execute — and the enemy's clock too."),
    ("civil", "Civil Considerations",
     "ASCOPE: areas, structures, capabilities, organizations, people, events."),
    ("informational", "Informational Considerations",
     "How information and the information environment affect the operation."),
]

ASCOPE = [
    ("areas", "Areas", "Districts, tribal boundaries, economic zones, no-go areas."),
    ("structures", "Structures", "Bridges, hospitals, mosques, government buildings, power plants."),
    ("capabilities", "Capabilities", "What the population can provide or needs — water, power, security, medical."),
    ("organizations", "Organizations", "NGOs, tribal councils, unions, religious bodies, criminal networks."),
    ("people", "People", "Key leaders, influencers, displaced persons, demographics."),
    ("events", "Events", "Elections, harvests, holidays, anniversaries, market days."),
]

OAKOC = [
    ("observation", "Observation and Fields of Fire"),
    ("avenues", "Avenues of Approach"),
    ("key_terrain", "Key Terrain"),
    ("obstacles", "Obstacles"),
    ("cover", "Cover and Concealment"),
]

WARFIGHTING_FUNCTIONS = [
    ("c2", "Command and Control", "S-3 / S-6",
     "Command posts, decision points, communications architecture."),
    ("movement_maneuver", "Movement and Maneuver", "S-3",
     "Moving forces to gain positional advantage."),
    ("intelligence", "Intelligence", "S-2",
     "Understanding the threat, terrain, weather, and civil considerations."),
    ("fires", "Fires", "FSO / FSCOORD",
     "Collective and coordinated use of fires — surface, air, and non-lethal."),
    ("sustainment", "Sustainment", "S-4 / S-1",
     "Logistics, personnel services, and health service support."),
    ("protection", "Protection", "S-3 Protection / PM / CBRN",
     "Preserving the force — security, survivability, CBRN, AMD, safety."),
]


# --------------------------------------------------------------------------
# Screening and evaluation criteria
# --------------------------------------------------------------------------

COA_SCREENING_CRITERIA = [
    ("feasible", "Feasible",
     "The unit has the time, space, and resources to do it."),
    ("acceptable", "Acceptable",
     "The cost in casualties, equipment, time, and position is worth the result."),
    ("suitable", "Suitable",
     "It accomplishes the mission and complies with the higher commander's intent."),
    ("distinguishable", "Distinguishable",
     "It is meaningfully different from the other COAs — not a re-shading."),
    ("complete", "Complete",
     "It answers what, when, where, how, and why, and accounts for the whole "
     "operation from start to end state."),
]

# Library the staff picks from in Step 2 (evaluation criteria are set before
# COAs exist, so the comparison in Step 5 is not rigged after the fact).
EVALUATION_CRITERIA_LIBRARY = [
    ("mission_accomplishment", "Mission Accomplishment",
     "Probability the COA achieves the stated end state."),
    ("risk_to_force", "Risk to Force",
     "Expected casualties and equipment losses relative to gain."),
    ("risk_to_mission", "Risk to Mission",
     "Probability of failure, and the consequence of that failure."),
    ("tempo", "Tempo / Speed",
     "How quickly the COA generates and sustains momentum."),
    ("flexibility", "Flexibility",
     "Ability to branch or sequel without a full replan."),
    ("simplicity", "Simplicity",
     "How easily subordinates will understand and execute it."),
    ("surprise", "Surprise",
     "Degree to which it strikes the enemy at a time or place they are "
     "unprepared for."),
    ("sustainment_feasibility", "Sustainment Feasibility",
     "Whether the concept of support can actually carry the concept of "
     "operations."),
    ("c2_requirements", "C2 Requirements",
     "Span of control, communications burden, and command post demands."),
    ("civil_considerations", "Civil Considerations",
     "Effect on the population, infrastructure, and host-nation relationships."),
    ("force_protection", "Force Protection",
     "Ability to preserve combat power against the threat's most dangerous "
     "capabilities."),
    ("intel_supportability", "Intelligence Supportability",
     "Whether collection can answer the PIRs this COA depends on."),
]


# --------------------------------------------------------------------------
# War gaming
# --------------------------------------------------------------------------

WARGAME_METHODS = [
    ("belt", "Belt",
     "Divide the AO into belts (usually phases or lateral strips) across the "
     "width of the sector and war game each belt in turn.",
     "Best when the operation is phased or the terrain divides cleanly. Gives "
     "the most complete look at synchronization across the whole force."),
    ("avenue_in_depth", "Avenue-in-Depth",
     "War game one avenue of approach at a time, from start to finish.",
     "Best for offensive operations and infiltration, or when avenues are "
     "clearly separated by terrain."),
    ("box", "Box",
     "Isolate a critical area — an objective, an engagement area, a river "
     "crossing — and war game it in fine detail.",
     "Best when time is short or when one event dominates the operation."),
]

WARGAME_RECORDING = [
    ("sync_matrix", "Synchronization Matrix",
     "Time or phase across the top, warfighting functions and units down the "
     "side. The standard product; produces the execution matrix directly."),
    ("sketch_note", "Sketch-Note",
     "A sketch of the action with numbered notes keyed to events. Faster, "
     "lower resolution, better for compressed timelines."),
]

WARGAME_SEQUENCE = [
    "Gather the tools (maps, overlays, running estimates, enemy templates).",
    "List all friendly forces available.",
    "List the assumptions in effect.",
    "List known critical events and decision points.",
    "Select the war-game method (belt, avenue-in-depth, or box).",
    "Select a technique to record and display results.",
    "War game the operation: action, reaction, counteraction.",
    "Assess the results and conduct the war-game brief.",
]


# --------------------------------------------------------------------------
# Risk management (ATP 5-19)
# --------------------------------------------------------------------------

RISK_PROBABILITY = ["Frequent", "Likely", "Occasional", "Seldom", "Unlikely"]
RISK_SEVERITY = ["Catastrophic", "Critical", "Moderate", "Negligible"]

# level lookup: RISK_MATRIX[severity][probability]
RISK_MATRIX = {
    "Catastrophic": {"Frequent": "Extremely High", "Likely": "Extremely High",
                     "Occasional": "High", "Seldom": "High", "Unlikely": "Moderate"},
    "Critical":     {"Frequent": "Extremely High", "Likely": "High",
                     "Occasional": "High", "Seldom": "Moderate", "Unlikely": "Low"},
    "Moderate":     {"Frequent": "High", "Likely": "Moderate",
                     "Occasional": "Moderate", "Seldom": "Low", "Unlikely": "Low"},
    "Negligible":   {"Frequent": "Moderate", "Likely": "Low",
                     "Occasional": "Low", "Seldom": "Low", "Unlikely": "Low"},
}

RISK_STEPS = [
    "Identify hazards.",
    "Assess hazards to determine risk.",
    "Develop controls and make risk decisions.",
    "Implement controls.",
    "Supervise and evaluate.",
]


def risk_level(severity, probability):
    """Return the composite risk level for a severity/probability pair."""
    return RISK_MATRIX.get(severity, {}).get(probability, "Unknown")


# --------------------------------------------------------------------------
# Operations, forms of maneuver, task verbs
# --------------------------------------------------------------------------

OPERATION_TYPES = [
    ("offense", "Offensive Operation",
     ["Movement to Contact", "Attack", "Exploitation", "Pursuit"]),
    ("defense", "Defensive Operation",
     ["Area Defense", "Mobile Defense", "Retrograde (Delay, Withdrawal, Retirement)"]),
    ("stability", "Stability Operation",
     ["Establish Civil Security", "Establish Civil Control",
      "Restore Essential Services", "Support to Governance",
      "Support to Economic and Infrastructure Development",
      "Conduct Security Cooperation"]),
    ("dsca", "Defense Support of Civil Authorities",
     ["Provide Support for Domestic Disasters",
      "Provide Support for Domestic CBRN Incidents",
      "Provide Support for Domestic Civilian Law Enforcement Agencies",
      "Provide Other Designated Support"]),
]

FORMS_OF_MANEUVER = [
    ("envelopment", "Envelopment",
     "Avoid the enemy's principal defenses to strike an assailable flank."),
    ("flank_attack", "Flank Attack",
     "A form of offensive maneuver directed at the flank of an enemy force."),
    ("frontal_attack", "Frontal Attack",
     "Strike the enemy across a wide front over the most direct approach. "
     "Least preferred; costly, but fastest to arrange."),
    ("infiltration", "Infiltration",
     "Move undetected through or into an area occupied by enemy forces to "
     "attack from an unexpected position."),
    ("penetration", "Penetration",
     "Concentrate to rupture the enemy defense on a narrow front and create "
     "assailable flanks."),
    ("turning_movement", "Turning Movement",
     "Pass around the enemy to seize an objective deep in their rear, forcing "
     "them to abandon their position."),
]

DEFENSIVE_FORMS = [
    ("area_defense", "Area Defense", "Deny the enemy designated terrain."),
    ("mobile_defense", "Mobile Defense",
     "Orient on destroying the enemy with a striking force."),
    ("delay", "Delay", "Trade space for time; avoid decisive engagement."),
    ("withdrawal", "Withdrawal", "Disengage and move away from the enemy."),
    ("retirement", "Retirement", "Move away from the enemy while not in contact."),
]

# Tactical mission tasks. The verb is the "what" in a mission statement.
TASK_VERBS = {
    "Effects on Enemy Force": [
        ("destroy", "Physically render an enemy force combat-ineffective until "
                    "it is reconstituted."),
        ("defeat", "Diminish the effectiveness of an enemy force to the point "
                   "it cannot accomplish its mission."),
        ("disrupt", "Break apart an enemy's formation or tempo, interrupt "
                    "their timetable, or cause premature commitment."),
        ("neutralize", "Render enemy personnel or materiel incapable of "
                       "interfering with a particular operation."),
        ("suppress", "Temporarily degrade the performance of a force or "
                     "weapons system below what is needed to accomplish its "
                     "mission."),
        ("block", "Deny the enemy access to an area or prevent their advance "
                  "in a direction."),
        ("fix", "Prevent the enemy from moving any part of their force from a "
                "specific location for a specific period."),
        ("isolate", "Seal off an enemy from their sources of support and deny "
                    "them freedom of movement."),
        ("canalize", "Restrict enemy movement to a narrow zone."),
        ("contain", "Stop, hold, or surround enemy forces, or cause them to "
                    "center their activity on a given front."),
        ("interdict", "Prevent, disrupt, or delay the enemy's use of an area "
                      "or route."),
    ],
    "Actions by Friendly Force": [
        ("attack", "Conduct an offensive operation to defeat, destroy, or "
                   "neutralize the enemy."),
        ("seize", "Take possession of a designated area by force."),
        ("secure", "Prevent a unit, facility, or area from being damaged or "
                   "destroyed as a result of enemy action."),
        ("clear", "Remove all enemy forces and eliminate organized resistance "
                  "within an assigned area."),
        ("occupy", "Move onto an area to control it, with or without force."),
        ("retain", "Ensure a terrain feature controlled by a friendly force "
                   "remains free of enemy occupation or use."),
        ("breach", "Break through or establish a passage through an enemy "
                   "defense, obstacle, or fortification."),
        ("bypass", "Maneuver around an obstacle, position, or enemy force to "
                   "maintain momentum."),
        ("exfiltrate", "Remove personnel or units from an area under enemy "
                       "control by stealth, deception, or surprise."),
        ("infiltrate", "Move covertly through or into an area occupied by "
                       "enemy or friendly forces."),
        ("follow_and_assume", "Follow a force conducting an offensive "
                              "operation and be prepared to continue the "
                              "mission if that force is fixed or attrited."),
        ("follow_and_support", "Follow and support a force conducting an "
                               "offensive operation."),
        ("screen", "Provide early warning to the main body."),
        ("guard", "Protect the main body by fighting to gain time while also "
                  "observing and reporting."),
        ("cover", "Operate apart from the main body to intercept, engage, "
                  "delay, disorganize, and deceive the enemy."),
        ("support_by_fire", "Engage the enemy by direct fire to support a "
                            "maneuvering force."),
        ("attack_by_fire", "Use direct fires, supported by indirect fires, to "
                           "engage an enemy without closing with them."),
        ("conduct_movement_to_contact",
         "Develop the situation and establish or regain contact."),
        ("defend", "Conduct a defensive operation to defeat an enemy attack, "
                   "gain time, or economize forces."),
        ("delay", "Trade space for time, inflict damage, and avoid decisive "
                  "engagement."),
        ("conduct_relief_in_place",
         "Replace all or part of a unit in an area with an incoming unit."),
        ("conduct_passage_of_lines",
         "Move a force through another force's positions to engage the enemy."),
    ],
}

# The "in order to" half of a mission statement.
PURPOSE_VERBS = [
    ("allow", "allow"), ("cause", "cause"), ("create", "create"),
    ("deceive", "deceive"), ("deny", "deny"), ("divert", "divert"),
    ("enable", "enable"), ("envelop", "envelop"), ("influence", "influence"),
    ("open", "open"), ("prevent", "prevent"), ("protect", "protect"),
    ("support", "support"), ("surprise", "surprise"),
]


# --------------------------------------------------------------------------
# Echelons and staff
# --------------------------------------------------------------------------

ECHELONS = [
    ("corps", "Corps", "divisions and separate brigades"),
    ("division", "Division", "brigade combat teams and functional brigades"),
    ("bct", "Brigade Combat Team (BCT)", "maneuver battalions, cavalry squadron, "
                                        "field artillery battalion, brigade "
                                        "engineer battalion, brigade support "
                                        "battalion"),
    ("brigade", "Functional / Multifunctional Brigade", "subordinate battalions"),
    ("battalion", "Battalion / Squadron", "companies, troops, or batteries"),
    ("company", "Company / Troop / Battery", "platoons"),
    ("platoon", "Platoon", "squads or sections"),
]

STAFF_SECTIONS = [
    ("cdr", "Commander", "Decides. Owns the intent and the risk."),
    ("xo", "Executive Officer / Chief of Staff",
     "Runs the staff and the planning timeline."),
    ("s1", "S-1 (Personnel)",
     "Strength reporting, replacements, casualty operations, personnel services."),
    ("s2", "S-2 (Intelligence)",
     "IPB, threat COAs, collection, PIR management."),
    ("s3", "S-3 (Operations)",
     "Plans, orders, task organization, training, current operations."),
    ("s4", "S-4 (Logistics)",
     "Supply, maintenance, transportation, field services."),
    ("s5", "S-5 (Plans)", "Future operations and long-range planning."),
    ("s6", "S-6 (Signal)", "Network, PACE plan, spectrum, communications security."),
    ("s7", "S-7 (Information Operations)",
     "Information effects, themes, messages."),
    ("s8", "S-8 (Financial Management)", "Resource management, contracting support."),
    ("s9", "S-9 (Civil Affairs)", "Civil considerations, host nation, CMO."),
    ("fso", "Fire Support Officer", "Fires planning, targeting, FSCMs."),
    ("eng", "Engineer", "Mobility, countermobility, survivability, general engineering."),
    ("adam", "Air Defense / Airspace Management",
     "Airspace control, air and missile defense."),
    ("cbrn", "CBRN Officer", "CBRN defense, hazard prediction, decontamination."),
    ("surg", "Surgeon", "Health service support, medical evacuation planning."),
    ("chap", "Chaplain", "Religious support planning."),
    ("sja", "Judge Advocate", "Legal review, ROE, detainee operations."),
    ("pao", "Public Affairs Officer", "Public information, media engagement."),
    ("oct", "Observer / Coach / Trainer",
     "Training observation and coaching (exercise use)."),
]


# --------------------------------------------------------------------------
# CCIR family
# --------------------------------------------------------------------------

CCIR_TYPES = [
    ("pir", "PIR — Priority Intelligence Requirement",
     "What the commander needs to know about the enemy, terrain, weather, or "
     "civil considerations to make a decision.",
     "Will the 2nd Battalion Tactical Group commit its reserve east of "
     "PHASE LINE BLUE before H+12?"),
    ("ffir", "FFIR — Friendly Force Information Requirement",
     "What the commander needs to know about their own force to make a "
     "decision.",
     "Does any maneuver company fall below 70% combat power?"),
]

EEFI_NOTE = ("EEFIs are essential elements of friendly information — what you "
             "must keep the threat from learning. Doctrinally EEFIs are not "
             "CCIRs, but they are managed alongside them and carry the same "
             "priority for the staff.")


# --------------------------------------------------------------------------
# WARNORD content (FM 6-0)
# --------------------------------------------------------------------------

WARNORD_CONTENT = {
    1: ["Type of operation", "General location of the operation",
        "Initial timeline", "Movement or reconnaissance to initiate"],
    2: ["Restated mission", "Commander's intent", "AO / area of interest",
        "CCIRs and EEFIs", "Risk guidance", "Priorities by warfighting function",
        "Military deception guidance", "Essential stability tasks",
        "Initial ISR plan", "Specific priorities", "Updated timeline",
        "Rehearsal guidance"],
    3: ["Mission", "Commander's intent", "Updated CCIRs and EEFIs",
        "Task organization", "Concept of operations sketch",
        "Tasks to subordinate units", "Coordinating instructions",
        "Updated timeline and rehearsal plan"],
}


# --------------------------------------------------------------------------
# OPORD structure (FM 6-0 five-paragraph field order)
# --------------------------------------------------------------------------
# Each entry: key, outline number, title, owning staff section, guidance shown
# to whoever is drafting it, and the flow fields that pre-populate the draft.

OPORD_SKELETON = [
    # --- Front matter ------------------------------------------------------
    {"key": "references", "num": "", "title": "References", "owner": "s3",
     "level": 0,
     "guidance": "Maps, charts, datums, and documents required to understand "
                 "the order. List map series, sheet name and number, edition, "
                 "and scale.",
     "from": ["references"]},
    {"key": "time_zone", "num": "", "title": "Time Zone Used Throughout the Order",
     "owner": "s3", "level": 0,
     "guidance": "One time zone for the whole order and all annexes.",
     "from": ["time_zone"]},
    {"key": "task_org", "num": "", "title": "Task Organization", "owner": "s3",
     "level": 0,
     "guidance": "How the force is organized for this operation. Either state "
                 "it here or refer to Annex A.",
     "from": ["task_organization"]},

    # --- 1. Situation ------------------------------------------------------
    {"key": "p1", "num": "1.", "title": "Situation", "owner": "s3", "level": 0,
     "container": True,
     "guidance": "The conditions the operation starts from.", "from": []},
    {"key": "p1a", "num": "a.", "title": "Area of Interest", "owner": "s2",
     "level": 1,
     "guidance": "The area of concern beyond the AO, including territory the "
                 "threat can influence from.",
     "from": ["area_of_interest"]},
    {"key": "p1b", "num": "b.", "title": "Area of Operations", "owner": "s2",
     "level": 1,
     "guidance": "Terrain and weather effects on friendly and threat "
                 "operations. Use OAKOC. Say what the effect is, not just what "
                 "the terrain is.",
     "from": ["terrain_effects", "weather_effects"]},
    {"key": "p1c", "num": "c.", "title": "Enemy Forces", "owner": "s2",
     "level": 1,
     "guidance": "Composition, disposition, strength, recent activity, "
                 "capabilities, most likely COA, and most dangerous COA.",
     "from": ["enemy_composition", "enemy_capabilities", "enemy_mlcoa",
              "enemy_mdcoa"]},
    {"key": "p1d", "num": "d.", "title": "Friendly Forces", "owner": "s3",
     "level": 1,
     "guidance": "Higher headquarters two levels up and one level up — mission "
                 "and intent. Then the missions of adjacent units left, right, "
                 "front, rear, and the reserve.",
     "from": ["higher_two_up", "higher_one_up"]},
    {"key": "p1e", "num": "e.",
     "title": "Interagency, Intergovernmental, and Nongovernmental Organizations",
     "owner": "s9", "level": 1,
     "guidance": "Organizations in the AO whose activity affects the "
                 "operation.",
     "from": []},
    {"key": "p1f", "num": "f.", "title": "Civil Considerations", "owner": "s9",
     "level": 1,
     "guidance": "ASCOPE. Focus on what changes friendly decisions.",
     "from": ["civil_considerations"]},
    {"key": "p1g", "num": "g.", "title": "Attachments and Detachments",
     "owner": "s3", "level": 1,
     "guidance": "Units attached to or detached from the command, with "
                 "effective times. The full laydown is in the task "
                 "organization above; list only what changes hands and when.",
     "from": []},
    {"key": "p1h", "num": "h.", "title": "Assumptions", "owner": "s3", "level": 1,
     "guidance": "Assumptions used to build the plan. Each one is valid, "
                 "necessary, and will be confirmed or denied.",
     "from": ["assumptions"]},

    # --- 2. Mission --------------------------------------------------------
    {"key": "p2", "num": "2.", "title": "Mission", "owner": "cdr", "level": 0,
     "guidance": "One sentence: who, what (task), when, where, and why "
                 "(purpose). No 'in order to' chains longer than one.",
     "from": ["mission_statement"]},

    # --- 3. Execution ------------------------------------------------------
    {"key": "p3", "num": "3.", "title": "Execution", "owner": "s3", "level": 0,
     "container": True,
     "guidance": "How the operation is conducted.", "from": []},
    {"key": "p3a", "num": "a.", "title": "Commander's Intent", "owner": "cdr",
     "level": 1,
     "guidance": "Expanded purpose, key tasks, and end state. Written so that "
                 "two levels down can act on it when the plan falls apart.",
     "from": ["intent_purpose", "intent_key_tasks", "intent_end_state"]},
    {"key": "p3b", "num": "b.", "title": "Concept of Operations", "owner": "s3",
     "level": 1,
     "guidance": "The decisive operation, shaping operations, and sustaining "
                 "operations, by phase. Name the main effort and when it "
                 "shifts.",
     "from": ["concept_of_operations", "approved_coa", "coa_modifications"]},
    {"key": "p3c", "num": "c.", "title": "Scheme of Movement and Maneuver",
     "owner": "s3", "level": 1,
     "guidance": "How maneuver forces move and fight, tied to the phases.",
     "from": ["scheme_maneuver"]},
    {"key": "p3d", "num": "d.", "title": "Scheme of Intelligence",
     "owner": "s2", "level": 1,
     "guidance": "How collection answers the PIRs, and who collects what, "
                 "when.",
     "from": ["scheme_intelligence"]},
    {"key": "p3e", "num": "e.", "title": "Scheme of Fires", "owner": "fso",
     "level": 1,
     "guidance": "Fire support tasks, priority of fires, and how fires support "
                 "the decisive operation.",
     "from": ["scheme_fires"]},
    {"key": "p3f", "num": "f.", "title": "Scheme of Protection", "owner": "eng",
     "level": 1,
     "guidance": "Survivability, CBRN, air and missile defense, personnel "
                 "recovery, and safety.",
     "from": ["scheme_protection"]},
    {"key": "p3g", "num": "g.", "title": "Tasks to Subordinate Units",
     "owner": "s3", "level": 1,
     "guidance": "One subparagraph per subordinate, in task-organization "
                 "order. Task and purpose for each.",
     "from": ["tasks_to_subordinates"]},
    {"key": "p3h", "num": "h.", "title": "Coordinating Instructions",
     "owner": "s3", "level": 1,
     "guidance": "Instructions that apply to two or more units: CCIRs, EEFIs, "
                 "ROE, risk reduction control measures, timeline, rehearsals, "
                 "reports.",
     "from": ["ccir_pir", "ccir_ffir", "eefi", "constraints", "decision_points",
              "rehearsals", "time_available", "final_guidance"]},

    # --- 4. Sustainment ----------------------------------------------------
    {"key": "p4", "num": "4.", "title": "Sustainment", "owner": "s4", "level": 0,
     "guidance": "The concept of support. If it cannot carry the concept of "
                 "operations, the plan is not feasible.",
     "from": ["sustainment_concept"]},
    {"key": "p4a", "num": "a.", "title": "Logistics", "owner": "s4", "level": 1,
     "guidance": "Maintenance, transportation, supply, field services, and "
                 "distribution. Where are the trains and when do they move?",
     "from": []},
    {"key": "p4b", "num": "b.", "title": "Personnel", "owner": "s1", "level": 1,
     "guidance": "Strength reporting, replacement operations, casualty "
                 "operations, and religious support.",
     "from": []},
    {"key": "p4c", "num": "c.", "title": "Health System Support", "owner": "surg",
     "level": 1,
     "guidance": "Medical evacuation, treatment, hospitalization, and Role 1/2 "
                 "locations.",
     "from": []},

    # --- 5. Command and Signal ---------------------------------------------
    {"key": "p5", "num": "5.", "title": "Command and Signal", "owner": "s6",
     "level": 0, "container": True,
     "guidance": "Where command is, and how it talks.", "from": []},
    {"key": "p5a", "num": "a.", "title": "Command", "owner": "s3", "level": 1,
     "guidance": "Location of the commander and key leaders, succession of "
                 "command, and liaison requirements.",
     "from": ["succession"]},
    {"key": "p5b", "num": "b.", "title": "Control", "owner": "s3", "level": 1,
     "guidance": "Command post locations and times of operation, and required "
                 "reports.",
     "from": ["command_posts"]},
    {"key": "p5c", "num": "c.", "title": "Signal", "owner": "s6", "level": 1,
     "guidance": "PACE plan, net structure, code words, recognition signals, "
                 "and communications windows.",
     "from": ["pace_plan"]},
]

# Annex lettering per FM 6-0. Subset that matters at BCT and below plus the
# common enablers; extend freely.
ANNEXES = [
    ("A", "Task Organization", "s3"),
    ("B", "Intelligence", "s2"),
    ("C", "Operations", "s3"),
    ("D", "Fires", "fso"),
    ("E", "Protection", "eng"),
    ("F", "Sustainment", "s4"),
    ("G", "Engineer", "eng"),
    ("H", "Signal", "s6"),
    ("J", "Public Affairs", "pao"),
    ("K", "Civil Affairs Operations", "s9"),
    ("L", "Information Collection", "s2"),
    ("M", "Assessment", "s5"),
    ("N", "Space Operations", "s3"),
    ("P", "Host-Nation Support", "s9"),
    ("R", "Reports", "s3"),
    ("U", "Inspector General", "cdr"),
    ("V", "Interagency Coordination", "s9"),
    ("W", "Operational Contract Support", "s8"),
    ("Z", "Distribution", "s3"),
]


# --------------------------------------------------------------------------
# Threat framework (TC 7-100 series / DATE)
# --------------------------------------------------------------------------

OPFOR_POSTURES = [
    ("peer", "Peer",
     "Comparable capability across most warfighting functions. Contests every "
     "domain, including space and cyberspace. Integrated air defense, "
     "long-range fires, and electromagnetic attack."),
    ("near_peer", "Near-Peer",
     "Overmatch in selected capabilities — usually fires, UAS, or EW — with "
     "gaps in sustainment or mobility."),
    ("hybrid", "Hybrid",
     "Regular forces operating alongside irregular forces, criminal elements, "
     "and information operations. Deniability is a weapon."),
    ("irregular", "Irregular",
     "Guerrilla, insurgent, and criminal elements. Avoids decisive engagement, "
     "attacks sustainment and the population's confidence."),
    ("combination", "Combination",
     "A regular force fixing you frontally while irregulars work your flanks "
     "and rear."),
]

OPFOR_TACTICAL_TASKS = [
    "Attack by fire", "Ambush", "Raid", "Reconnaissance attack",
    "Disruption attack", "Fixing attack", "Assault", "Complex battle position",
    "Simple battle position", "Area defense", "Maneuver defense",
    "Withdrawal under pressure", "Counterattack",
]

# DATE-style notional locales. Fully fictional; used so scenarios never
# reference a real place by accident.
DATE_ENVIRONMENTS = [
    ("caucasus", "DATE Caucasus",
     ["Atropia", "Donovia", "Ariana", "Limaria", "Gorgas"],
     "Mixed mountain and coastal plain, heavy mechanized threat, contested "
     "energy infrastructure."),
    ("pacific", "DATE Pacific",
     ["Belesia", "Olvana", "North Torbia", "South Torbia"],
     "Maritime and littoral, archipelagic terrain, long lines of "
     "communication, contested sea and air approaches."),
    ("europe", "DATE Europe",
     ["Bothnia", "Framland", "Torrike", "Pirtuni"],
     "Improved road network, dense civilian population, near-peer ground "
     "combat with long-range fires."),
    ("africa", "DATE Africa",
     ["Amari", "Nyumba", "Kujenga", "Ziwa"],
     "Sparse infrastructure, extended sustainment distances, hybrid threat "
     "with strong irregular component."),
    ("custom", "Custom / Home Station",
     [],
     "Locally defined training area and notional country set."),
]


# --------------------------------------------------------------------------
# Helper lookups
# --------------------------------------------------------------------------

def staff_section_name(key):
    for k, name, _desc in STAFF_SECTIONS:
        if k == key:
            return name
    return key.upper()


def all_task_verbs():
    """Flat list of (verb, definition) across all categories."""
    out = []
    for _cat, items in TASK_VERBS.items():
        out.extend(items)
    return out


def task_verb_definition(verb):
    for v, d in all_task_verbs():
        if v == verb:
            return d
    return ""


def opord_node(key):
    for node in OPORD_SKELETON:
        if node["key"] == key:
            return node
    return None
