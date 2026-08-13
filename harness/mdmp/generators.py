"""Deterministic, doctrine-driven option generators.

These run with no model, no network, and no GPU. They read the answers already
in the plan and compose candidate options from the doctrinal structures in
doctrine.py. The result is never a blank box: even on a disconnected laptop the
staff always gets something concrete to accept, edit, or argue with.

When a language model *is* configured, the same field asks the model for the
same shape of options (see harness/agent/providers.py) and these become the
fallback. Both paths return the identical contract, so the interface and the
OPORD assembly do not care which one ran.

Every generator has the signature:

    gen(ctx: dict, n: int) -> list[dict]

where each returned dict has: label, value, rationale, and optional flags.
`value` is a string for choice/text fields, and one candidate entry for
items/table fields (a string, or a list of cells).
"""

from harness.mdmp import doctrine as D

REGISTRY = {}


def generator(name):
    def wrap(fn):
        REGISTRY[name] = fn
        return fn
    return wrap


# --------------------------------------------------------------- utilities --

def _env(ctx):
    key = (ctx.get("oe_framework") or "caucasus").lower()
    for k, name, countries, desc in D.DATE_ENVIRONMENTS:
        if k in key or name.lower() in key:
            return k, name, countries, desc
    return D.DATE_ENVIRONMENTS[0]


def _country(ctx, idx=0, default="ATROPIA"):
    _k, _n, countries, _d = _env(ctx)
    if not countries:
        return default
    return countries[idx % len(countries)].upper()


def _threat_country(ctx):
    return _country(ctx, 1, "DONOVIA")


def _friendly_country(ctx):
    return _country(ctx, 0, "ATROPIA")


def _unit(ctx):
    return ctx.get("unit_designation") or "2d Brigade Combat Team"


def _echelon_key(ctx):
    val = (ctx.get("echelon") or "bct").lower()
    for k, name, _sub in D.ECHELONS:
        if k in val or name.lower().startswith(val[:6]):
            return k
    return "bct"


def _higher_echelon(ctx):
    order = ["platoon", "company", "battalion", "bct", "division", "corps"]
    k = _echelon_key(ctx)
    i = order.index(k) if k in order else 3
    one = order[min(i + 1, len(order) - 1)]
    two = order[min(i + 2, len(order) - 1)]
    names = dict((a, b) for a, b, _c in D.ECHELONS)
    return names.get(one, "Division"), names.get(two, "Corps")


def _subordinates(ctx):
    k = _echelon_key(ctx)
    table = {
        "corps": ["1st Division", "2d Division", "3d Division",
                  "Division Artillery", "Sustainment Brigade"],
        "division": ["1st BCT", "2d BCT", "3d BCT", "Division Artillery",
                     "Combat Aviation Brigade", "Division Sustainment Brigade"],
        "bct": ["1-11 IN", "2-11 IN", "3-11 IN", "1-7 CAV (Cavalry Squadron)",
                "2-14 FA (Field Artillery)", "52d BEB (Engineer)",
                "552d BSB (Support)"],
        "brigade": ["1st Battalion", "2d Battalion", "3d Battalion",
                    "Forward Support Company"],
        "battalion": ["A Company", "B Company", "C Company", "D Company",
                      "HHC", "Mortar Platoon", "Scout Platoon"],
        "company": ["1st Platoon", "2d Platoon", "3d Platoon",
                    "Weapons Squad", "HQ Section"],
        "platoon": ["1st Squad", "2d Squad", "3d Squad", "Weapons Squad"],
    }
    return table.get(k, table["bct"])


def _optype(ctx):
    val = (ctx.get("operation_type") or "offense").lower()
    if "defen" in val and "support" not in val:
        return "defense"
    if "stab" in val:
        return "stability"
    if "dsca" in val or "civil authorit" in val:
        return "dsca"
    return "offense"


def _posture(ctx):
    val = (ctx.get("opfor_posture") or "near-peer").lower()
    for k, name, desc in D.OPFOR_POSTURES:
        if k.replace("_", "-") in val.replace("_", "-") or name.lower() in val:
            return k, name, desc
    return D.OPFOR_POSTURES[1]


def _phases(ctx):
    t = _optype(ctx)
    if t == "defense":
        return ["Phase I — Preparation", "Phase II — Shaping / Counter-recon",
                "Phase III — Decisive Defense", "Phase IV — Counterattack",
                "Phase V — Consolidation"]
    if t == "stability":
        return ["Phase I — Assessment", "Phase II — Establish Security",
                "Phase III — Restore Services", "Phase IV — Transition"]
    if t == "dsca":
        return ["Phase I — Alert and Movement", "Phase II — Immediate Response",
                "Phase III — Sustained Support", "Phase IV — Transition and "
                "Redeployment"]
    return ["Phase I — Preparation", "Phase II — Movement to the LD",
            "Phase III — Decisive Operation", "Phase IV — Consolidation and "
            "Reorganization", "Phase V — Transition"]


# Notional graphic control measures, three deconflicted name sets so that
# alternative options do not all use the same words.
_GRAPHICS = [
    {"pl": ["PHASE LINE BLUE", "PHASE LINE GOLD", "PHASE LINE STEEL"],
     "obj": ["OBJECTIVE FALCON", "OBJECTIVE HAWK"], "axis": "AXIS EAGLE",
     "ea": "ENGAGEMENT AREA COBRA", "nai": "NAI 1", "tai": "TAI 3",
     "bp": "BATTLE POSITION 12"},
    {"pl": ["PHASE LINE COPPER", "PHASE LINE JADE", "PHASE LINE IRON"],
     "obj": ["OBJECTIVE BADGER", "OBJECTIVE OTTER"], "axis": "AXIS WOLF",
     "ea": "ENGAGEMENT AREA VIPER", "nai": "NAI 4", "tai": "TAI 7",
     "bp": "BATTLE POSITION 20"},
    {"pl": ["PHASE LINE AMBER", "PHASE LINE SLATE", "PHASE LINE FLINT"],
     "obj": ["OBJECTIVE LANCE", "OBJECTIVE SABER"], "axis": "AXIS BISON",
     "ea": "ENGAGEMENT AREA HORNET", "nai": "NAI 9", "tai": "TAI 11",
     "bp": "BATTLE POSITION 33"},
]


def _g(i):
    return _GRAPHICS[i % len(_GRAPHICS)]


def opt(label, value, rationale="", flags=None):
    return {"label": label, "value": value, "rationale": rationale,
            "flags": list(flags or [])}


# ============================================================ STEP 1 ========

@generator("unit_designation")
def gen_unit(ctx, n=4):
    return [
        opt("2d Brigade Combat Team, 52d Infantry Division",
            "2d Brigade Combat Team, 52d Infantry Division",
            "Standard notional BCT designation used in most exercise packets."),
        opt("1st Battalion, 11th Infantry", "1st Battalion, 11th Infantry",
            "Battalion-level training audience."),
        opt("3d Squadron, 7th Cavalry", "3d Squadron, 7th Cavalry",
            "Reconnaissance and security focused audience."),
        opt("52d Division", "52d Division",
            "Division staff training audience."),
    ][:n]


@generator("echelon")
def gen_echelon(ctx, n=8):
    # Brigade combat team first: it is the most common training audience and
    # it matches the default unit designation.
    order = ["bct", "battalion", "company", "division", "brigade", "platoon",
             "corps"]
    rows = sorted(D.ECHELONS,
                  key=lambda e: order.index(e[0]) if e[0] in order else 99)
    return [opt(name, name, "Subordinates: %s." % sub)
            for _k, name, sub in rows][:n]


@generator("operation_type")
def gen_optype(ctx, n=12):
    out = []
    for _k, family, forms in D.OPERATION_TYPES:
        for form in forms:
            out.append(opt("%s — %s" % (family.split()[0], form),
                           "%s: %s" % (family, form),
                           "One of the %s listed in FM 3-0."
                           % family.lower()))
    return out[:n]


@generator("oe_framework")
def gen_oe(ctx, n=6):
    out = []
    for _k, name, countries, desc in D.DATE_ENVIRONMENTS:
        label = name
        extra = (" Notional states: %s." % ", ".join(countries)) if countries else ""
        out.append(opt(label, name, desc + extra))
    return out[:n]


@generator("opfor_posture")
def gen_posture(ctx, n=6):
    return [opt(name, name, desc) for _k, name, desc in D.OPFOR_POSTURES][:n]


@generator("higher_two_up")
def gen_two_up(ctx, n=3):
    one, two = _higher_echelon(ctx)
    fc, tc = _friendly_country(ctx), _threat_country(ctx)
    t = _optype(ctx)
    out = []
    if t == "offense":
        out.append(opt(
            "%s attacks to restore the border" % two,
            "%s attacks no later than D+3 to defeat %s forces west of the "
            "international boundary in order to restore the sovereign border of "
            "%s and set conditions for follow-on stability operations.\n\n"
            "Intent: The purpose of this operation is to remove the threat's "
            "ability to hold %s territory. Key tasks are to defeat the threat's "
            "forward divisions, protect the population centres along the "
            "coastal corridor, and retain freedom of movement on the main "
            "supply routes. End state: threat forces destroyed or withdrawn "
            "east of the boundary, host-nation government functioning, "
            "friendly forces postured for transition."
            % (two, tc.title(), fc.title(), fc.title()),
            "Two-up mission for an offensive campaign; gives the purpose your "
            "own mission statement will nest inside."))
        out.append(opt(
            "%s conducts a movement to contact" % two,
            "%s conducts a movement to contact along the northern corridor "
            "beginning D-Day to develop the situation and establish contact "
            "with %s forces in order to determine the enemy's main defensive "
            "belt.\n\nIntent: Find the enemy before he finds us and on our "
            "terms. Key tasks: maintain contact once gained, avoid decisive "
            "engagement by the covering force, preserve combat power for the "
            "main body. End state: enemy main defensive belt located and "
            "templated, friendly forces uncommitted and postured to attack."
            % (two, tc.title()),
            "Use when the higher fight is still developing and the situation "
            "is vague — which is the normal case at the start of an exercise."))
    elif t == "defense":
        out.append(opt(
            "%s defends to retain key terrain" % two,
            "%s defends in sector from D-Day to defeat the %s first-echelon "
            "attack and retain the coastal highway in order to preserve the "
            "lodgement for follow-on forces.\n\nIntent: We trade no ground we "
            "cannot retake. Key tasks: destroy the enemy's breach capability, "
            "retain the port and the airfield, preserve a mobile reserve. End "
            "state: enemy first echelon defeated forward of the highway, "
            "friendly forces able to transition to the offense."
            % (two, tc.title()),
            "Standard two-up defensive framing with a clearly stated retained "
            "terrain requirement."))
    elif t == "stability":
        out.append(opt(
            "%s sets conditions for host-nation transition" % two,
            "%s conducts stability operations throughout the province to "
            "establish civil security and restore essential services in order "
            "to enable transition of security responsibility to host-nation "
            "forces.\n\nIntent: The population's confidence is the objective. "
            "Key tasks: protect population centres, restore water and power, "
            "partner with host-nation security forces. End state: host-nation "
            "forces capable of independent security operations, essential "
            "services restored to pre-conflict levels." % two,
            "Frames the fight around the population rather than the threat."))
    else:
        out.append(opt(
            "%s supports the lead federal agency" % two,
            "%s provides defense support of civil authorities throughout the "
            "affected region on order to save lives, mitigate suffering, and "
            "protect property in support of the designated lead federal "
            "agency.\n\nIntent: We support; we do not lead. Key tasks: "
            "establish liaison with civil authorities, provide life-sustaining "
            "support, protect critical infrastructure. End state: civil "
            "authorities capable of managing the response, military support "
            "withdrawn." % two,
            "DSCA framing; note the supporting — not supported — relationship."))
    out.append(opt(
        "Write the two-up mission myself",
        "", "Use this when you are working from a real higher order in hand."))
    return out[:n]


@generator("higher_one_up")
def gen_one_up(ctx, n=3):
    one, _two = _higher_echelon(ctx)
    unit = _unit(ctx)
    tc = _threat_country(ctx)
    t = _optype(ctx)
    g = _g(0)
    out = []
    if t == "offense":
        out.append(opt(
            "%s attacks with two brigades forward" % one,
            "%s attacks at H-Hour to defeat the %s 2d Tactical Group in zone "
            "in order to secure the crossings over the river line and enable "
            "the division's exploitation to the east.\n\n"
            "Concept of operations: The %s attacks with two brigades forward "
            "and one in reserve. The main effort is the northern brigade, "
            "attacking along %s to seize %s. Supporting effort in the south "
            "fixes the enemy's southern regiment. The reserve is prepared to "
            "pass through the main effort on order.\n\n"
            "Your role: %s is %s the supporting effort in the south."
            % (one, tc.title(), one, g["axis"], g["obj"][0], unit,
               "one of the two brigades forward, and is"),
            "Gives you a clear task, a clear purpose, and a named role in the "
            "higher concept — everything mission analysis needs."))
    elif t == "defense":
        out.append(opt(
            "%s defends forward with a mobile reserve" % one,
            "%s defends in sector NLT D-1 to defeat the %s first echelon "
            "forward of %s in order to retain the divisional support area and "
            "preserve combat power for the counterattack.\n\n"
            "Concept of operations: Two brigades defend forward in prepared "
            "positions; the cavalry squadron screens forward of %s to provide "
            "early warning and force the enemy to deploy early. The reserve is "
            "prepared to counterattack into %s on order.\n\n"
            "Your role: %s defends in the northern sector."
            % (one, tc.title(), g["pl"][1], g["pl"][0], g["ea"], unit),
            "Establishes retained terrain, the screen, and the counterattack "
            "condition — the three things a defensive plan hangs on."))
    elif t == "stability":
        out.append(opt(
            "%s partners across three districts" % one,
            "%s conducts stability operations in the province to establish "
            "civil security and support host-nation governance in order to set "
            "conditions for transition.\n\nConcept of operations: Each "
            "subordinate unit partners with a host-nation security element in "
            "its district, prioritising the district centres and the market "
            "corridor. Civil affairs teams lead assessment of essential "
            "services.\n\nYour role: %s is responsible for the northern "
            "district." % (one, unit),
            "Assigns a geographic area and a partnering relationship."))
    else:
        out.append(opt(
            "%s establishes a base of support operations" % one,
            "%s establishes support operations in the affected area on order "
            "to provide logistics, engineering, and medical support in "
            "support of the lead civil authority.\n\nConcept of operations: "
            "Subordinate units establish distribution points in each affected "
            "county, coordinate through the joint field office, and operate "
            "under the direction of the civil incident commander.\n\nYour role: "
            "%s supports the northern counties." % (one, unit),
            "Keeps the supporting relationship explicit, which is the most "
            "commonly missed piece in DSCA planning."))
    out.append(opt(
        "Same mission, but you are the main effort",
        (out[0]["value"].replace("supporting effort in the south",
                                 "MAIN EFFORT in the north")
         if out and out[0]["value"] else ""),
        "Changing which effort you are changes your priority of fires and "
        "sustainment — worth planning both ways."))
    out.append(opt("Write the one-up order myself", "",
                   "Paste in the real higher order if you have it."))
    return out[:n]


@generator("time_available")
def gen_time(ctx, n=8):
    return [
        opt("WARNORD #1 issued", ["WARNORD #1 issued", "H-72", "XO"], ""),
        opt("Mission analysis brief", ["Mission analysis brief", "H-60", "Staff"], ""),
        opt("WARNORD #2 issued", ["WARNORD #2 issued", "H-58", "S-3"], ""),
        opt("COA development complete", ["COA development complete", "H-48", "S-3"], ""),
        opt("COA brief to commander", ["COA brief to commander", "H-44", "Staff"], ""),
        opt("War game complete", ["War game complete", "H-36", "Staff"], ""),
        opt("COA decision brief", ["COA decision brief", "H-30", "Staff"], ""),
        opt("WARNORD #3 issued", ["WARNORD #3 issued", "H-28", "S-3"], ""),
        opt("OPORD published", ["OPORD published", "H-24", "S-3"], ""),
        opt("Confirmation briefs", ["Confirmation briefs", "H-22", "Subordinate CDRs"], ""),
        opt("Combined arms rehearsal", ["Combined arms rehearsal", "H-12", "All"], ""),
        opt("Execution (H-Hour)", ["Execution (H-Hour)", "H-Hour", "All"], ""),
    ][:n]


@generator("initial_guidance")
def gen_initial_guidance(ctx, n=3):
    t = _optype(ctx)
    return [
        opt("Full MDMP, two COAs, standard timeline",
            "Run the full process. I want two developed courses of action, not "
            "three thin ones. The S-2 starts IPB immediately and gives me an "
            "initial threat picture at the mission analysis brief. The "
            "cavalry squadron begins movement to its screen line now — do not "
            "wait for the order. Use the 1/3 – 2/3 rule: my staff owns the "
            "first third of the time, subordinates own the rest. Issue "
            "WARNORD #1 within the hour.",
            "The default when time is adequate."),
        opt("Time-constrained: abbreviated MDMP, one COA",
            "We do not have time for the full process. I am directing an "
            "abbreviated MDMP. Develop one course of action based on my "
            "guidance and refine it during the war game rather than comparing "
            "alternatives. The S-2 gives me the most likely enemy COA only — "
            "we will handle the most dangerous COA as a branch. Subordinates "
            "get a WARNORD in thirty minutes with enough to start their own "
            "planning and movement.",
            "Use when the timeline is compressed. Doctrinally sound: the "
            "commander may direct which steps to abbreviate.",
            ["Accepting risk: no COA comparison"]),
        opt("Reconnaissance-pull: hold planning until we see the enemy",
            "I am not going to lock a plan before we know where the enemy is. "
            "The cavalry squadron moves now and develops the situation. The "
            "staff runs mission analysis in parallel and produces a framework "
            "with branches rather than a single scheme. I will make the COA "
            "decision once reconnaissance answers PIR 1. Plan on a decision at "
            "H-30 and an order at H-24."
            if t == "offense" else
            "I want the engagement areas developed before we finalise the "
            "scheme. Engineers and the fire support officer walk the ground "
            "with the company commanders today. The staff builds the plan "
            "around what we can actually cover with direct and indirect fire, "
            "not around what looks clean on the map.",
            "Reconnaissance-pull planning. Slower to a fixed plan, much "
            "better fit to the actual ground."),
    ][:n]


# ============================================================ STEP 2 ========

@generator("area_of_interest")
def gen_aoi(ctx, n=3):
    tc, fc = _threat_country(ctx), _friendly_country(ctx)
    g = _g(0)
    return [
        opt("Corridor out to the threat's operational depth",
            "The area of interest extends from the forward line of own troops "
            "east to the %s operational reserve assembly areas, approximately "
            "150 kilometres, and 40 kilometres north and south of the assigned "
            "boundaries. It includes the two hard-surface routes the threat "
            "must use to reinforce, the rail head at the district centre, and "
            "the airfield capable of supporting rotary-wing operations. %s and "
            "%s are the named areas of interest that will confirm or deny "
            "reinforcement." % (tc.title(), g["nai"], g["tai"]),
            "Sized to the threat's ability to influence you within your "
            "planning horizon — the usual test for an area of interest."),
        opt("Tight area of interest — close fight only",
            "The area of interest extends 25 kilometres beyond the forward "
            "boundary, covering the threat's direct fire and short-range "
            "indirect fire systems and the two secondary routes into the "
            "sector. It does not include the operational depth, which the "
            "higher headquarters covers.",
            "Appropriate at battalion and below, or when higher owns deep "
            "collection.",
            ["Risk: misses long-range fires and reinforcement"]),
        opt("Extended area of interest including the information environment",
            "The area of interest includes the physical corridor to the "
            "threat's operational depth, plus the population centres in %s "
            "whose media and social networks shape the narrative in the "
            "sector, and the maritime approaches that support threat "
            "resupply." % fc.title(),
            "Adds the informational and maritime dimensions — the (I) in "
            "METT-TC (I)."),
    ][:n]


@generator("terrain_effects")
def gen_terrain(ctx, n=10):
    g = _g(0)
    return [
        opt("Observation — dominant ridge",
            "OBSERVATION AND FIELDS OF FIRE: The ridge north of %s dominates "
            "the sector and gives whoever holds it observation over both "
            "avenues of approach out to 8 kilometres. Losing it blinds our "
            "fires." % g["obj"][0], ""),
        opt("Avenue — northern high-speed corridor",
            "AVENUES OF APPROACH: The northern hard-surface route supports a "
            "battalion-sized mounted force moving two abreast. It is the "
            "fastest approach for both sides and the most likely threat "
            "counterattack route.", ""),
        opt("Avenue — southern restricted approach",
            "AVENUES OF APPROACH: The southern approach is restricted by "
            "irrigation canals and supports dismounted or light vehicle "
            "movement only. It is slow but concealed.", ""),
        opt("Key terrain — the crossing site",
            "KEY TERRAIN: The bridge and adjacent ford are the only crossings "
            "within the sector that support tracked vehicles. Whoever controls "
            "them controls the tempo of the operation for both sides.", ""),
        opt("Key terrain — the district centre",
            "KEY TERRAIN: The district centre is key terrain for its road "
            "junction and its influence on the population, not for its "
            "elevation.", ""),
        opt("Obstacle — the canal system",
            "OBSTACLES: The irrigation canal network runs perpendicular to our "
            "axis and restricts movement to existing crossings. Expect the "
            "threat to have reinforced these with mines and wire.", ""),
        opt("Obstacle — urban density",
            "OBSTACLES: Built-up areas along the route reduce our formation "
            "options to column and canalize mounted movement onto two streets, "
            "both of which are ideal ambush sites.", ""),
        opt("Cover and concealment — favours the defender",
            "COVER AND CONCEALMENT: Tree lines and the canal berms give the "
            "defender covered positions with short fields of fire. Attacking "
            "forces are exposed in the open ground between them for roughly "
            "600 metres.", ""),
        opt("Cover and concealment — limited for us",
            "COVER AND CONCEALMENT: There is almost no natural concealment "
            "from aerial observation in the western half of the sector. Assume "
            "threat unmanned systems can see our assembly areas.", ""),
        opt("Trafficability degrades with rain",
            "OBSTACLES: Off-road trafficability drops to restricted for "
            "wheeled vehicles within six hours of significant rainfall. The "
            "plan should not depend on cross-country wheeled movement.", ""),
    ][:n]


@generator("weather_effects")
def gen_weather(ctx, n=8):
    return [
        opt("Illumination — limited visibility favours us",
            "ILLUMINATION: Moonrise at 0230 with 22% illumination. Limited "
            "visibility from 2100 to 0230 favours our thermal-equipped force "
            "over the threat's largely image-intensifier equipped force.", ""),
        opt("Ceiling — grounds rotary wing",
            "CLOUD COVER AND CEILING: Ceiling forecast at 400 feet with "
            "visibility under 1 mile between 0400 and 0900. Rotary-wing "
            "support and most unmanned systems are unavailable during that "
            "window — including the threat's.", ""),
        opt("Wind — affects obscuration and CBRN",
            "WIND: Sustained 15 knots from the west, gusting 25. Smoke "
            "obscuration will drift onto our own southern approach; any CBRN "
            "hazard will move toward the population centre.", ""),
        opt("Precipitation — degrades mobility",
            "PRECIPITATION: 20mm expected over 24 hours. Off-road mobility for "
            "wheeled vehicles degrades to restricted; expect the threat to "
            "canalize onto the same routes we are.", ""),
        opt("Temperature — cold weather injury risk",
            "TEMPERATURE AND HUMIDITY: Overnight lows near freezing with high "
            "humidity. Cold weather injury risk is significant for dismounted "
            "troops in static positions; plan warming and rotation.", ""),
        opt("Heat — degrades dismounted tempo",
            "TEMPERATURE AND HUMIDITY: Daytime highs above 38°C. Dismounted "
            "operations will be limited to roughly two hours of sustained work "
            "without rest and water resupply.", ""),
        opt("Visibility — dust and obscuration",
            "VISIBILITY: Blowing dust reduces optical and thermal ranges by "
            "roughly half during afternoon hours, closing engagement ranges "
            "and favouring the side that has planned for close fight.", ""),
        opt("Sunrise / sunset — timing the attack",
            "LIGHT DATA: BMNT 0512, sunrise 0541, sunset 1917, EENT 1946. A "
            "dawn attack puts the sun behind us and in the defender's optics.",
            ""),
    ][:n]


@generator("enemy_composition")
def gen_enemy_comp(ctx, n=3):
    pk, pname, _pdesc = _posture(ctx)
    tc = _threat_country(ctx)
    out = []
    if pk in ("peer", "near_peer"):
        out.append(opt(
            "Mechanized tactical group, two battalions forward",
            "The %s 2d Tactical Group is defending in sector with two "
            "mechanized infantry battalions forward and one tank battalion in "
            "reserve, supported by an artillery battalion of 152mm "
            "self-propelled howitzers and an integrated short-range air "
            "defense battery. Estimated strength is 85%% across the forward "
            "battalions and near 100%% in the reserve. Over the last 72 hours "
            "the group has been improving survivability positions, emplacing "
            "obstacles along the canal line, and conducting reconnaissance "
            "with small unmanned systems twice daily." % tc.title(),
            "A doctrinal TC 7-100 tactical group laydown at the scale a BCT "
            "would face."))
        out.append(opt(
            "Attacking echelon in the movement to contact",
            "The %s 4th Tactical Group is advancing west along the northern "
            "corridor with a reconnaissance detachment forward, a "
            "first-echelon mechanized battalion following at 15 kilometres, "
            "and the remainder of the group in march column. Strength is "
            "assessed at near full. The group has not yet deployed into "
            "combat formation, which suggests they have not located us."
            % tc.title(),
            "Use for a movement to contact or a meeting engagement."))
    elif pk == "irregular":
        out.append(opt(
            "Irregular network, cellular structure",
            "The threat in sector is an irregular network of an estimated 120 "
            "to 180 fighters organised in cells of six to ten, with a "
            "supporting network of financiers, facilitators, and sympathetic "
            "population. Armament is small arms, medium machine guns, "
            "rocket-propelled grenades, commercial unmanned systems modified to "
            "drop munitions, and improvised explosive devices. The network "
            "avoids sustained contact and attacks logistics convoys and "
            "static checkpoints, averaging four incidents per week over the "
            "last month.",
            "Sized and behaviourally described rather than laid out on a map — "
            "which is the honest way to render an irregular threat."))
    else:
        out.append(opt(
            "Hybrid: regular battalion plus irregular network",
            "The threat is a hybrid force: one %s mechanized infantry "
            "battalion at approximately 80%% strength holding the district "
            "centre, operating alongside an irregular network of roughly 150 "
            "fighters in the surrounding villages. The regular element "
            "provides fires and command and control; the irregular element "
            "provides early warning, IED emplacement, and deniable attacks on "
            "our sustainment." % tc.title(),
            "Hybrid threats are the DATE default and the hardest to template "
            "because the two elements operate on different logic."))
    out.append(opt("Write the enemy laydown myself", "",
                   "Use when the S-2 already has a threat template built."))
    return out[:n]


@generator("enemy_capabilities")
def gen_enemy_caps(ctx, n=10):
    pk, _n, _d = _posture(ctx)
    common = [
        opt("Indirect fires", "FIRES: Can mass battalion-level 152mm fires on "
            "two targets simultaneously with a response time of 4 to 8 minutes "
            "from acquisition, out to 24 kilometres.", ""),
        opt("Counter-battery", "FIRES: Counter-battery radar coverage over the "
            "forward sector; expect counter-fire within 6 minutes of our first "
            "rounds. Shoot-and-scoot is mandatory, not optional.", ""),
        opt("Unmanned aerial systems", "RECONNAISSANCE: Persistent small "
            "unmanned aerial reconnaissance over the forward sector during "
            "daylight, with a demonstrated ability to cue indirect fires "
            "inside 10 minutes.", ""),
        opt("Electromagnetic attack", "EW: Can jam FM voice and disrupt GPS "
            "over a 20 kilometre radius for periods of 30 to 60 minutes, and "
            "will direction-find and target our command posts by their "
            "emissions.", ""),
        opt("Air defense", "AIR DEFENSE: Short-range air defense systems "
            "protect the forward battalions, denying rotary-wing operations "
            "below 3,000 feet within 12 kilometres of their positions.", ""),
        opt("Obstacles and mining", "MOBILITY: Can emplace a company-width "
            "reinforcing obstacle belt with scatterable mines in under two "
            "hours using its engineer element.", ""),
        opt("Information operations", "INFORMATION: Actively contests the "
            "narrative through local and social media, and will publicise any "
            "civilian casualty within hours, accurate or not.", ""),
        opt("Armored counterattack", "MANEUVER: Retains a tank-heavy reserve "
            "capable of a counterattack of up to battalion strength with a "
            "commitment time of 45 to 90 minutes.", ""),
        opt("Improvised explosive devices", "MOBILITY: Emplaces command-wire "
            "and victim-operated IEDs on predictable routes, concentrated at "
            "choke points and previously used halt locations.", ""),
        opt("Cyberspace and network attack", "CYBER: Has demonstrated intrusion "
            "attempts against coalition and host-nation logistics networks; "
            "assume our unclassified sustainment traffic is read.", ""),
    ]
    if pk == "irregular":
        order = [8, 6, 2, 0, 9, 3, 5, 1, 4, 7]
        return [common[i] for i in order][:n]
    return common[:n]


@generator("enemy_mlcoa")
def gen_mlcoa(ctx, n=3):
    tc = _threat_country(ctx)
    t = _optype(ctx)
    g = _g(0)
    if t == "defense":
        base = ("MOST LIKELY: The %s tactical group attacks along the northern "
                "corridor with two battalions forward and one in second "
                "echelon, preceded by 20 to 30 minutes of preparatory fires on "
                "our forward battle positions and a reconnaissance detachment "
                "probing for gaps. The main attack fixes our northern company "
                "team while the second echelon attempts to penetrate at the "
                "boundary between our two forward battalions — the seam is the "
                "most attractive point on the ground and their doctrine tells "
                "them to look for it. Expected timeline: probes from H-2, "
                "preparatory fires H-hour, assault H+0:30, second echelon "
                "committed by H+3." % tc.title())
    else:
        base = ("MOST LIKELY: The %s tactical group defends from prepared "
                "positions along %s with two battalions forward, using the "
                "canal line as a reinforcing obstacle covered by direct fire "
                "and pre-planned artillery targets. A reconnaissance "
                "detachment screens forward to give early warning and cue "
                "fires. The reserve tank battalion is held 10 to 15 kilometres "
                "back, prepared to counterattack into any penetration within "
                "60 to 90 minutes of commitment."
                % (tc.title(), g["pl"][0]))
    return [
        opt("Doctrinal template — the by-the-book fight", base,
            "The MLCOA should be what the threat's own doctrine tells them to "
            "do, adjusted for the terrain — not what would be most convenient "
            "for us."),
        opt("Economy of force forward, weight elsewhere",
            base.replace("MOST LIKELY:", "MOST LIKELY:") +
            "\n\nVariation: the threat treats our sector as economy of force, "
            "holding with a reduced element and weighting the adjacent sector. "
            "Indicators would be a thinner forward screen, reduced artillery "
            "responsiveness, and displacement of air defense southward.",
            "Worth templating when your sector is not obviously the decisive "
            "one for the enemy."),
        opt("Write the MLCOA myself", "",
            "Use the S-2's own threat template if it is already built."),
    ][:n]


@generator("enemy_mdcoa")
def gen_mdcoa(ctx, n=3):
    tc = _threat_country(ctx)
    t = _optype(ctx)
    g = _g(0)
    if t == "defense":
        base = ("MOST DANGEROUS: The threat masses both echelons on a single "
                "narrow front at the boundary between our forward battalions, "
                "preceded by massed fires including persistent chemical "
                "employment on our reserve assembly area to prevent "
                "commitment. Simultaneous electromagnetic attack blinds our "
                "command net during the penetration. If the penetration "
                "succeeds before our reserve can move, the threat reaches the "
                "brigade support area within four hours and the defense "
                "collapses from the rear.")
    else:
        base = ("MOST DANGEROUS: Rather than defending forward, the threat "
                "accepts our penetration of the first belt and commits the "
                "tank reserve early into a prepared engagement area behind "
                "%s, catching our lead battalion at its most extended and "
                "least supported moment — after the breach, before "
                "consolidation. Massed artillery, including scatterable mines "
                "emplaced behind us, isolates the lead battalion from "
                "reinforcement for 60 to 90 minutes." % g["pl"][1])
    return [
        opt("Counterattack into our transition point", base,
            "The MDCOA is the most damaging COA that remains possible — not "
            "the least likely one you can imagine. This one attacks the moment "
            "we are most vulnerable."),
        opt("Attack our sustainment instead of our maneuver",
            "MOST DANGEROUS: The threat declines the fight forward and instead "
            "concentrates unmanned systems, long-range fires, and irregular "
            "elements against our sustainment — the support area, the "
            "distribution routes, and the medical evacuation chain. Our "
            "maneuver units are untouched and combat-ineffective within 72 "
            "hours because they cannot be resupplied. This is dangerous "
            "precisely because it does not look like an attack until it is "
            "already working.",
            "The sustainment-focused MDCOA is under-templated and repeatedly "
            "punishes units in training.",
            ["Drives sustainment protection and route security tasks"]),
        opt("Write the MDCOA myself", "", ""),
    ][:n]


@generator("civil_considerations")
def gen_civil(ctx, n=10):
    fc = _friendly_country(ctx)
    return [
        opt("Areas — displaced persons corridor",
            "AREAS: The main east–west highway is the displaced persons route. "
            "Expect civilian movement to conflict directly with our "
            "sustainment traffic during the first 48 hours.", ""),
        opt("Areas — contested district boundary",
            "AREAS: The district boundary north of the objective separates two "
            "communities with a history of land disputes. Our presence will be "
            "read as favouring whichever side we operate from.", ""),
        opt("Structures — the hospital",
            "STRUCTURES: The provincial hospital sits 400 metres from the "
            "objective and is the only surgical facility within 60 kilometres. "
            "It is a protected site and a decisive point for the population's "
            "confidence.", ""),
        opt("Structures — water treatment plant",
            "STRUCTURES: The water treatment plant supplies 40,000 people. "
            "Damage to it creates a humanitarian problem within 72 hours that "
            "we will own.", ""),
        opt("Capabilities — power is intermittent",
            "CAPABILITIES: Municipal power runs 6 to 8 hours per day. Any "
            "further degradation is attributed to us regardless of cause.", ""),
        opt("Organizations — NGO presence",
            "ORGANIZATIONS: Two international non-governmental organizations "
            "operate clinics in the sector. They will not co-locate with us "
            "and their movement must be deconflicted, not directed.", ""),
        opt("Organizations — tribal council",
            "ORGANIZATIONS: The district council meets weekly and is the "
            "practical authority in the villages, more so than the formal "
            "government. Their acquiescence matters more than their "
            "endorsement.", ""),
        opt("People — key leader",
            "PEOPLE: The district governor is the recognised %s government "
            "authority but spends most weeks in the provincial capital. The "
            "deputy is the person actually present and actually consulted."
            % fc.title(), ""),
        opt("Events — market day",
            "EVENTS: Market day is every Tuesday, drawing 2,000 to 3,000 "
            "people into the district centre between 0700 and 1400. Operations "
            "there on a Tuesday carry a much higher civilian casualty risk.",
            ""),
        opt("Events — religious observance",
            "EVENTS: A significant religious observance falls during the "
            "planned execution window. Operations during it will be read as "
            "deliberate provocation whether or not they are.", ""),
    ][:n]


@generator("specified_tasks")
def gen_specified(ctx, n=8):
    t = _optype(ctx)
    g = _g(0)
    if t == "defense":
        pool = [
            "Defend in sector NLT D-1 (higher OPORD, para 3g).",
            "Retain %s (higher OPORD, para 3a key tasks)." % g["pl"][0],
            "Establish a screen forward of %s NLT D-2 (higher OPORD, para 3c)." % g["pl"][0],
            "Be prepared to counterattack into %s on order (higher OPORD, para 3g)." % g["ea"],
            "Maintain contact with 1st Brigade on the northern boundary (para 3h).",
            "Report combat power daily at 0600 and 1800 (para 3h).",
            "Provide one company team as division reserve NLT D+1 (para 3g).",
            "Emplace obstacle belt along the canal line NLT D-1 (Annex G).",
        ]
    elif t == "stability":
        pool = [
            "Establish civil security in the northern district (higher OPORD, para 3g).",
            "Partner with host-nation security forces in the district (para 3g).",
            "Restore water service to the district centre NLT D+30 (para 3g).",
            "Conduct weekly key leader engagement with the district council (para 3h).",
            "Report essential service status weekly (para 3h).",
            "Do not conduct unilateral operations without host-nation presence (para 3h).",
            "Support the district election in coordination with civil affairs (Annex K).",
            "Assess and report on host-nation force readiness monthly (Annex M).",
        ]
    else:
        pool = [
            "Attack along %s at H-Hour (higher OPORD, para 3g)." % g["axis"],
            "Seize %s NLT H+6 (higher OPORD, para 3g)." % g["obj"][0],
            "Secure the crossing site at the bridge (higher OPORD, para 3g).",
            "Be prepared to continue the attack east on order (para 3g).",
            "Maintain contact with the adjacent brigade on the southern boundary (para 3h).",
            "Do not damage the bridge — it is required for follow-on forces (para 3h).",
            "Provide one company team to the brigade reserve NLT H-2 (para 3g).",
            "Establish a passage point for the cavalry squadron's rearward passage (para 3h).",
        ]
    return [opt(p.split("(")[0].strip().rstrip("."), p,
                "Stated in the higher order — quote it rather than paraphrase.")
            for p in pool][:n]


@generator("implied_tasks")
def gen_implied(ctx, n=8):
    t = _optype(ctx)
    g = _g(0)
    if t == "defense":
        pool = [
            "Conduct counter-reconnaissance forward of the battle positions to "
            "deny the threat observation of our preparations.",
            "Rehearse the counterattack, including the route and the passage of "
            "lines, before the threat's expected attack window.",
            "Harden and camouflage command posts against unmanned aerial "
            "observation and counter-fire.",
            "Establish and rehearse a casualty evacuation plan that works while "
            "under indirect fire.",
            "Coordinate obstacle emplacement with the adjacent unit so the belts "
            "tie in at the boundary.",
            "Displace artillery after each fire mission to survive counter-fire.",
            "Establish a deception effort to draw the threat's main attack away "
            "from the boundary seam.",
            "Pre-position Class IV and V forward for obstacle emplacement.",
        ]
    else:
        pool = [
            "Conduct a forward passage of lines through the cavalry squadron "
            "prior to crossing the line of departure.",
            "Breach the obstacle belt along the canal line to open the axis "
            "for the main body.",
            "Suppress threat air defense along %s to enable rotary-wing "
            "support to the objective." % g["axis"],
            "Establish a support-by-fire position covering the objective before "
            "the assault element is committed.",
            "Consolidate and reorganise on the objective and prepare for the "
            "expected counterattack.",
            "Establish a casualty collection point forward that can operate "
            "inside artillery range.",
            "Secure the crossing site against irregular attack once seized — "
            "seizing it and holding it are different tasks.",
            "Deconflict fires with the adjacent unit across the boundary "
            "before the assault.",
        ]
    return [opt(p.split(".")[0][:60], p,
                "Not stated in the higher order, but required to accomplish "
                "the mission. Routine SOP tasks are excluded.")
            for p in pool][:n]


@generator("essential_tasks")
def gen_essential(ctx, n=6):
    t = _optype(ctx)
    g = _g(0)
    if t == "defense":
        pool = [
            "Defeat the threat's first-echelon attack forward of %s." % g["pl"][1],
            "Retain %s." % g["pl"][0],
            "Preserve the counterattack force for commitment on order.",
            "Deny the threat penetration at the boundary seam.",
        ]
    elif t == "stability":
        pool = [
            "Establish civil security in the district centre.",
            "Restore water service to the district centre.",
            "Build host-nation security force capability to independent "
            "operation.",
        ]
    else:
        pool = [
            "Seize %s." % g["obj"][0],
            "Secure the crossing site intact.",
            "Defeat the threat forces defending west of the river.",
            "Preserve combat power for the continuation of the attack east.",
        ]
    return [opt(p.rstrip("."), p,
                "An essential task must be executed or the mission fails. "
                "These go directly into the mission statement.")
            for p in pool][:n]


@generator("constraints")
def gen_constraints(ctx, n=8):
    return [
        opt("Must attack no earlier than H-Hour",
            "CONSTRAINT: Do not cross the line of departure before H-Hour — "
            "the adjacent unit's supporting fires are timed to it.", ""),
        opt("Must retain a reserve",
            "CONSTRAINT: Retain no less than one company team as a reserve "
            "throughout the operation.", ""),
        opt("Must preserve the bridge",
            "RESTRAINT: Do not damage or destroy the bridge. Follow-on forces "
            "depend on it.", ""),
        opt("No unilateral operations",
            "RESTRAINT: Do not conduct operations in the district without "
            "host-nation security force participation.", ""),
        opt("No fires into the built-up area without approval",
            "RESTRAINT: Indirect fires into the district centre require "
            "approval at the next higher headquarters.", ""),
        opt("Must report combat power on a fixed schedule",
            "CONSTRAINT: Report combat power at 0600 and 1800 daily.", ""),
        opt("Must maintain contact on the boundary",
            "CONSTRAINT: Maintain physical contact with the adjacent unit on "
            "the northern boundary throughout.", ""),
        opt("No movement outside the assigned axis",
            "RESTRAINT: Do not manoeuvre outside the assigned axis without "
            "clearance — the adjacent unit's fires are planned into that "
            "space.", ""),
    ][:n]


@generator("facts")
def gen_facts(ctx, n=8):
    unit = _unit(ctx)
    return [
        opt("Our combat power", "%s is at 92%% assigned strength; all maneuver "
            "companies are above 85%% operational readiness." % unit, ""),
        opt("Class III on hand", "The unit holds 2.5 days of supply of Class "
            "III(B) and 1.5 combat loads of Class V forward.", ""),
        opt("Crossing sites", "There are two crossing sites in sector; only one "
            "supports tracked vehicles.", ""),
        opt("Adjacent unit posture", "The adjacent brigade to the north crosses "
            "the line of departure at the same H-Hour.", ""),
        opt("Rotary wing availability", "Rotary-wing medical evacuation is "
            "available from the division support area with a 25-minute "
            "response time in visual conditions.", ""),
        opt("Threat last observed", "The threat's forward battalions were last "
            "confirmed in their current positions 18 hours ago by aerial "
            "imagery.", ""),
        opt("Population", "The district population is approximately 40,000, "
            "concentrated in the district centre and four villages.", ""),
        opt("Communications range", "FM voice range in sector is limited to "
            "12 kilometres by terrain; retransmission is required to reach the "
            "southern company.", ""),
    ][:n]


@generator("assumptions")
def gen_assumptions(ctx, n=8):
    return [
        opt("No threat reinforcement before H+24",
            "ASSUMPTION: The threat does not reinforce the sector with "
            "operational reserves before H+24. (Confirm or deny via PIR 1.)",
            "An assumption must be necessary, valid, and later confirmed or "
            "denied — this one names the PIR that will do so."),
        opt("Adjacent unit crosses on time",
            "ASSUMPTION: The adjacent brigade crosses the line of departure on "
            "time and fixes the threat's northern battalion. (Confirm via "
            "liaison at H-4.)", ""),
        opt("Bridge remains intact",
            "ASSUMPTION: The bridge is not destroyed before we reach it. "
            "(Confirm via reconnaissance NLT H-2; branch plan required if "
            "denied.)", "", ["Drives a branch plan"]),
        opt("Weather permits aviation",
            "ASSUMPTION: Ceiling and visibility permit rotary-wing support "
            "during the assault. (Confirm at the H-6 weather update.)", ""),
        opt("Host-nation forces participate",
            "ASSUMPTION: Host-nation security forces participate as planned "
            "and at the strength committed. (Confirm at the D-1 coordination "
            "meeting.)", ""),
        opt("Civilian population does not mass on the route",
            "ASSUMPTION: Displaced civilian movement does not close the main "
            "supply route during the operation. (Confirm via civil affairs "
            "reporting daily.)", ""),
        opt("Sustainment throughput holds",
            "ASSUMPTION: The division can push one Class III/V resupply "
            "forward per 24 hours despite threat interdiction. (Confirm with "
            "the support battalion at H-12.)", ""),
        opt("Communications degraded but not denied",
            "ASSUMPTION: Threat electromagnetic attack degrades but does not "
            "deny FM voice for periods longer than one hour. (Drives the PACE "
            "plan.)", ""),
    ][:n]


@generator("shortfalls")
def gen_shortfalls(ctx, n=6):
    return [
        opt("Breaching assets", "SHORTFALL: One mine-clearing line charge "
            "short of the two required for a two-lane breach. Requesting from "
            "division; otherwise accept a single-lane breach and the resulting "
            "reduction in tempo.", ""),
        opt("Counter-UAS", "SHORTFALL: No dedicated counter-unmanned aerial "
            "system capability. Mitigation is passive: dispersion, camouflage, "
            "and emissions discipline.", ""),
        opt("Medical evacuation", "SHORTFALL: One ground ambulance short per "
            "maneuver battalion. Mitigation is pre-positioning non-standard "
            "casualty evacuation platforms.", ""),
        opt("Retransmission", "SHORTFALL: Insufficient retransmission teams to "
            "cover both the southern company and the support area. Requesting "
            "one team from the signal company.", ""),
        opt("Class V forward", "SHORTFALL: Only 1.5 combat loads of Class V "
            "forward against a planning requirement of 2. Accepting risk "
            "through H+12 with resupply timed to the consolidation.", ""),
        opt("Interpreters", "SHORTFALL: Two interpreters against a requirement "
            "of five for sustained engagement across four villages.", ""),
    ][:n]


@generator("problem_statement")
def gen_problem(ctx, n=3):
    t = _optype(ctx)
    g = _g(0)
    if t == "defense":
        base = ("The unit must defeat a numerically superior threat attack "
                "along a frontage wider than doctrinal templates support, "
                "without ceding %s, while the boundary seam between the two "
                "forward battalions remains the most attractive penetration "
                "point on the ground and cannot be covered by direct fire from "
                "either side alone." % g["pl"][0])
    else:
        base = ("The unit must seize %s and secure the crossing site intact "
                "against a prepared defense that is protected by a reinforcing "
                "obstacle belt and covered by responsive indirect fire, while "
                "preserving enough combat power to continue the attack east."
                % g["obj"][0])
    return [
        opt("Terrain and tempo framing", base,
            "A problem statement names the gap and the obstacle. If it reads "
            "like a restatement of the mission, it is not doing any work."),
        opt("Time framing",
            base + " The binding constraint is time: the threat's reserve can "
            "reach the objective in 60 to 90 minutes, so any scheme that does "
            "not consolidate within that window invites a counterattack "
            "against an unconsolidated force.",
            "Same problem framed around the clock rather than the ground — "
            "often the sharper framing."),
        opt("Write the problem statement myself", "", ""),
    ][:n]


@generator("mission_statement")
def gen_mission(ctx, n=4):
    unit = _unit(ctx)
    t = _optype(ctx)
    g = _g(0)
    ess = ctx.get("essential_tasks") or []
    first = ess[0] if ess and isinstance(ess, list) else None
    out = []
    if t == "defense":
        out.append(opt(
            "Defend to retain — standard form",
            "%s defends in sector NLT 010600Z to defeat the %s first-echelon "
            "attack forward of %s in order to retain %s and preserve the "
            "division's ability to transition to the offense."
            % (unit, _threat_country(ctx).title(), g["pl"][1], g["pl"][0]),
            "Who / what / when / where / why, one sentence, one purpose."))
        out.append(opt(
            "Defend to preserve the force",
            "%s defends in sector NLT 010600Z to defeat the threat's "
            "first-echelon attack in order to preserve combat power for the "
            "division counterattack." % unit,
            "Same task, different purpose — the purpose changes what you are "
            "willing to trade.",
            ["Changes what terrain you will give up"]))
    elif t == "stability":
        out.append(opt(
            "Stability — security first",
            "%s conducts stability operations in the northern district "
            "beginning 010001Z to establish civil security and restore "
            "essential services in order to enable transition of security "
            "responsibility to host-nation forces." % unit, ""))
    else:
        out.append(opt(
            "Attack to seize — standard form",
            "%s attacks along %s at 010500Z to seize %s and secure the "
            "crossing site in order to enable the division's exploitation "
            "east of the river." % (unit, g["axis"], g["obj"][0]),
            "Who / what / when / where / why. Note the two essential tasks "
            "carried into one sentence without an 'in order to' chain."))
        out.append(opt(
            "Attack to defeat — enemy-oriented",
            "%s attacks along %s at 010500Z to defeat the %s forces defending "
            "west of the river in order to enable the division's exploitation "
            "east." % (unit, g["axis"], _threat_country(ctx).title()),
            "Oriented on the enemy rather than the terrain. Choose "
            "deliberately: it changes what 'done' means.",
            ["Enemy-oriented: success is measured by their state, not yours"]))
    if first:
        out.append(opt(
            "Built from your first essential task",
            "%s %s NLT 010600Z in order to %s."
            % (unit, str(first).rstrip("."),
               "enable the higher headquarters' concept of operations"),
            "Assembled directly from the essential task you selected — edit "
            "the purpose to match your higher commander's intent."))
    out.append(opt("Write the mission statement myself", "", ""))
    return out[:n]


@generator("intent_purpose")
def gen_intent_purpose(ctx, n=3):
    t = _optype(ctx)
    return [
        opt("Broader purpose — enable the higher fight",
            "The purpose of this operation is to remove the threat's ability "
            "to contest the river line so the division can exploit east "
            "without pausing. We are not here to hold ground; we are here to "
            "open a door and keep it open."
            if t != "defense" else
            "The purpose of this operation is to buy the division the time it "
            "needs to mass its counterattack force. Every hour we hold is an "
            "hour the division uses. We are not trying to win here; we are "
            "trying to make winning possible somewhere else.",
            "Intent purpose is broader than the mission statement's 'in order "
            "to' — it explains why this operation exists in the larger fight."),
        opt("Purpose framed around the force",
            "The purpose of this operation is to accomplish the mission with "
            "the force intact enough to fight again tomorrow. I would rather "
            "arrive on the objective slower and whole than fast and spent.",
            "Explicitly states a preservation bias, which subordinates need to "
            "hear if they are going to make the right call without you."),
        opt("Write the intent purpose myself", "", ""),
    ][:n]


@generator("intent_key_tasks")
def gen_key_tasks(ctx, n=8):
    t = _optype(ctx)
    if t == "defense":
        pool = [
            "Defeat the threat's breach capability before it reaches the "
            "obstacle belt.",
            "Retain the ability to counterattack — the reserve is not "
            "committed to the forward fight.",
            "Deny the threat the boundary seam.",
            "Maintain a common understanding of the situation across the "
            "brigade even when communications degrade.",
            "Protect the sustainment area — the defense fails from the rear "
            "before it fails from the front.",
        ]
    else:
        pool = [
            "Maintain the tempo of the attack once contact is made.",
            "Preserve the crossing site intact.",
            "Isolate the objective before the assault element is committed.",
            "Consolidate fast enough to defeat the counterattack.",
            "Keep the sustainment tail closed up with the maneuver force.",
            "Retain freedom of movement on the axis behind us.",
        ]
    return [opt(p.split(" —")[0][:58], p,
                "A key task is a condition the force must achieve. It is not "
                "tied to one COA and it is not a task to a specific unit.")
            for p in pool][:n]


@generator("intent_end_state")
def gen_end_state(ctx, n=3):
    t = _optype(ctx)
    g = _g(0)
    if t == "defense":
        base = ("FRIENDLY: The brigade holds %s with all three maneuver "
                "battalions combat-effective and the reserve uncommitted or "
                "reconstituted. THREAT: The first-echelon attack is defeated, "
                "with the threat unable to resume the attack for at least 48 "
                "hours. TERRAIN: %s and the main supply route remain under our "
                "control. CIVIL: The population centre is undamaged and the "
                "displaced persons route remains open."
                % (g["pl"][0], g["pl"][0]))
    else:
        base = ("FRIENDLY: The brigade is consolidated on %s with the crossing "
                "site secured, at no less than 75%% combat power, and postured "
                "to continue the attack east on order. THREAT: Threat forces "
                "west of the river are defeated — destroyed, withdrawn, or "
                "incapable of organised resistance. TERRAIN: The crossing site "
                "is intact and trafficable to tracked vehicles. CIVIL: The "
                "district centre and the hospital are undamaged and the "
                "population has not been displaced by our operation."
                % g["obj"][0])
    return [
        opt("Four-part end state (friendly / threat / terrain / civil)", base,
            "End state describes conditions, not actions. Covering all four "
            "elements is what makes it usable by a subordinate."),
        opt("End state with an explicit combat power floor",
            base + " If achieving this end state would take the brigade below "
            "65%% combat power, I want to be told before the assault is "
            "committed, not after.",
            "Naming a number turns the end state into something a subordinate "
            "can measure against in the moment.",
            ["Ties directly to an FFIR"]),
        opt("Write the end state myself", "", ""),
    ][:n]


@generator("ccir_pir")
def gen_pir(ctx, n=8):
    g = _g(0)
    tc = _threat_country(ctx)
    return [
        opt("Reserve commitment",
            "PIR 1: Will the %s tactical group commit its tank reserve, and "
            "if so where and when? (Decision: commit our reserve / shift "
            "priority of fires. Look at %s and %s.)"
            % (tc.title(), g["nai"], g["tai"]), ""),
        opt("Obstacle belt composition",
            "PIR 2: What is the composition and depth of the obstacle belt "
            "along the canal line? (Decision: number of breach lanes and "
            "allocation of breaching assets.)", ""),
        opt("Bridge status",
            "PIR 3: Is the bridge prepared for demolition? (Decision: commit "
            "the crossing-site seizure force early, or accept a wet gap "
            "crossing.)", ""),
        opt("Air defense laydown",
            "PIR 4: Where are the threat's short-range air defense systems? "
            "(Decision: rotary-wing routing and SEAD allocation.)", ""),
        opt("Reinforcement",
            "PIR 5: Will the threat reinforce the sector from operational "
            "depth before H+24? (Decision: request division shaping fires.)",
            ""),
        opt("Counter-battery radar",
            "PIR 6: Where is the threat's counter-battery radar? (Decision: "
            "artillery positioning and displacement timeline.)", ""),
        opt("Irregular activity pattern",
            "PIR 7: Are irregular elements emplacing IEDs on our planned main "
            "supply route? (Decision: route selection and clearance "
            "priority.)", ""),
        opt("Population movement",
            "PIR 8: Will displaced civilians close the main supply route "
            "during the operation? (Decision: alternate route activation.)",
            ""),
    ][:n]


@generator("ccir_ffir")
def gen_ffir(ctx, n=8):
    return [
        opt("Combat power threshold",
            "FFIR 1: Any maneuver company falls below 70% combat power.", ""),
        opt("Breaching capability loss",
            "FFIR 2: Loss of two or more breaching systems.", ""),
        opt("Class III / V status",
            "FFIR 3: Any battalion falls below one combat load of Class V or "
            "one day of supply of Class III.", ""),
        opt("Command post loss",
            "FFIR 4: Loss of a command post or the commander's ability to "
            "command.", ""),
        opt("Communications denial",
            "FFIR 5: Loss of communications with any subordinate battalion "
            "exceeding 30 minutes.", ""),
        opt("Casualty evacuation saturation",
            "FFIR 6: Casualty evacuation capacity exceeded at any collection "
            "point.", ""),
        opt("Reserve commitment",
            "FFIR 7: Commitment of the brigade reserve.", ""),
        opt("Adjacent unit failure",
            "FFIR 8: Adjacent unit fails to cross the line of departure on "
            "time or is unable to fix its assigned threat element.", ""),
    ][:n]


@generator("eefi")
def gen_eefi(ctx, n=6):
    return [
        opt("Location of the main effort",
            "EEFI 1: The location and identity of the main effort.", ""),
        opt("Timing of the attack",
            "EEFI 2: The timing of the attack, including H-Hour.", ""),
        opt("Reserve location and composition",
            "EEFI 3: The location, composition, and commitment criteria of the "
            "reserve.", ""),
        opt("Breach locations",
            "EEFI 4: The planned breach locations and the number of lanes.",
            ""),
        opt("Command post locations",
            "EEFI 5: The locations of the command posts and the timing of "
            "their displacement.", ""),
        opt("Sustainment node locations",
            "EEFI 6: The location of the support area and the timing of "
            "logistics packages.", ""),
    ][:n]


@generator("eval_criteria")
def gen_eval(ctx, n=12):
    return [opt(name, name, desc)
            for _k, name, desc in D.EVALUATION_CRITERIA_LIBRARY][:n]


@generator("planning_guidance")
def gen_planning_guidance(ctx, n=3):
    t = _optype(ctx)
    return [
        opt("Guidance by warfighting function",
            "MOVEMENT AND MANEUVER: Develop two courses of action. One must "
            "use the northern approach, one the southern — I want the "
            "trade-off on the table, not assumed away. Keep a company team "
            "uncommitted in both.\n"
            "INTELLIGENCE: Answer PIR 1 before the COA decision brief. Focus "
            "collection on the reserve, not on the forward positions we "
            "already know about.\n"
            "FIRES: Plan for counter-fire from the first round. I want "
            "displacement built into the scheme, not added later.\n"
            "SUSTAINMENT: Show me the concept of support at the COA brief. If "
            "it cannot carry the concept of operations, I want to know before "
            "the war game, not during it.\n"
            "PROTECTION: Assume the threat sees our assembly areas. Plan "
            "dispersion and deception accordingly.\n"
            "RISK: I will accept moderate risk to the force to achieve "
            "surprise. I will not accept high risk to the mission.",
            "The standard form — guidance by warfighting function, which is "
            "how the staff is organised to receive it."),
        opt("Narrow guidance — one COA, refine in the war game",
            "Develop one course of action along the northern approach. Do not "
            "spend time on alternatives we will not run. I want the war game "
            "to make it better, not to choose between options. Intelligence "
            "priority is the reserve. Fires priority is counter-fire "
            "survivability. I accept moderate risk to force, low risk to "
            "mission.",
            "Fits a compressed timeline; pairs with abbreviated MDMP.",
            ["No COA comparison — decision is made up front"]),
        opt("Write the planning guidance myself", "", ""),
    ][:n]


# ============================================================ STEP 3 ========

@generator("combat_power")
def gen_combat_power(ctx, n=3):
    return [
        opt("Function-by-function comparison",
            "MOVEMENT AND MANEUVER: Roughly 1.4:1 in our favour in mounted "
            "combat systems, but the threat is defending prepared positions, "
            "which by the usual planning ratio means we do not have the 3:1 "
            "advantage a deliberate attack against prepared defenses wants. "
            "Advantage: marginal, ours.\n"
            "INTELLIGENCE: We have better sensors; they have better local "
            "knowledge and a shorter sensor-to-shooter loop. Advantage: even.\n"
            "FIRES: They out-range us and have counter-battery radar. We have "
            "more responsive close air support when weather permits. "
            "Advantage: theirs, in most conditions.\n"
            "SUSTAINMENT: We have depth; they have short lines. Over 72 hours, "
            "advantage: ours.\n"
            "PROTECTION: They have integrated short-range air defense; we have "
            "no counter-UAS. Advantage: theirs.\n"
            "CONCLUSION: We win a long fight and lose a fires duel. The scheme "
            "should close quickly and avoid trading artillery.",
            "Comparing by function rather than counting vehicles is what makes "
            "this step useful — and the conclusion line is what the commander "
            "actually reads."),
        opt("Ratio-focused assessment",
            "Force ratio in the sector is approximately 1.4:1 in mounted "
            "combat systems and 1:1.2 in tube artillery. Against a prepared "
            "defense the planning ratio for a deliberate attack is 3:1 at the "
            "point of penetration, which we can only achieve by weighting one "
            "approach heavily and accepting economy of force elsewhere. That "
            "requirement should drive COA development, not be discovered "
            "during the war game.",
            "Leads directly into a weighted-penetration COA."),
        opt("Write the assessment myself", "", ""),
    ][:n]


@generator("coa_statement")
def gen_coa(ctx, n=4):
    t = _optype(ctx)
    unit = _unit(ctx)
    subs = _subordinates(ctx)
    a, b, c = (subs + subs)[0], (subs + subs)[1], (subs + subs)[2]
    g0, g1, g2 = _g(0), _g(1), _g(2)
    if t == "defense":
        return [
            opt("Defend forward — weight the likely penetration point",
                "FORM: Area defense, weighted north.\n"
                "DECISIVE OPERATION: %s defends %s to defeat the threat's "
                "first-echelon main attack in %s.\n"
                "SHAPING: %s screens forward of %s to force early deployment "
                "and cue fires, then conducts a rearward passage of lines. %s "
                "defends the southern sector as an economy of force with one "
                "company team.\n"
                "RESERVE: One company team, positioned central, prepared to "
                "counterattack into %s or to block a southern penetration.\n"
                "MAIN EFFORT: %s during the decisive defense; shifts to the "
                "reserve on commitment.\n"
                "FIRES: Priority to the decisive operation; final protective "
                "fires planned forward of each battle position; counter-fire "
                "on call.\n"
                "END STATE: Threat first echelon defeated forward of %s; "
                "reserve uncommitted or reconstituted."
                % (a, g0["bp"], g0["ea"], c, g0["pl"][0], b, g0["ea"], a,
                   g0["pl"][1]),
                "Concentrates on the templated main attack. Simple, strong "
                "where the enemy is expected, thin everywhere else.",
                ["Risk: if the MLCOA is wrong, the weighted flank is empty"]),
            opt("Mobile defense — trade space, strike the penetration",
                "FORM: Mobile defense.\n"
                "DECISIVE OPERATION: The striking force (%s, reinforced) "
                "attacks the penetrating threat element in %s once it is "
                "committed and extended.\n"
                "SHAPING: %s and %s conduct a fixing defense along %s, "
                "yielding ground deliberately to draw the threat into the "
                "engagement area.\n"
                "MAIN EFFORT: The fixing force until the threat is committed, "
                "then the striking force.\n"
                "FIRES: Priority to shaping the penetration into %s; "
                "obstacles turn rather than block.\n"
                "END STATE: Threat penetrating force destroyed in %s; original "
                "positions restored or not, as the commander decides."
                % (a, g1["ea"], b, c, g1["pl"][0], g1["ea"], g1["ea"]),
                "Genuinely different from the first COA: it accepts "
                "penetration on purpose. Requires more mobility and more "
                "nerve.",
                ["Requires a mobile striking force", "Gives up ground early"]),
            opt("Defend in depth — successive positions",
                "FORM: Area defense in depth.\n"
                "DECISIVE OPERATION: %s defends successive positions from %s "
                "to %s, attriting the threat at each and displacing before "
                "decisive engagement.\n"
                "SHAPING: %s screens; %s prepares the final position and "
                "receives the displacing force through a rearward passage of "
                "lines.\n"
                "MAIN EFFORT: Shifts rearward with the defense.\n"
                "END STATE: Threat culminates forward of the final position "
                "having lost the initiative and at least a third of its "
                "combat power."
                % (a, g2["pl"][0], g2["pl"][2], c, b),
                "Buys the most time and preserves the force best; gives up the "
                "most ground.",
                ["Not viable if terrain must be retained"]),
            opt("Write this COA myself", "", ""),
        ][:n]
    return [
        opt("Penetration in the north — weight one approach",
            "FORM OF MANEUVER: Penetration along the northern approach.\n"
            "DECISIVE OPERATION: %s attacks along %s to seize %s.\n"
            "SHAPING: %s conducts a supporting attack in the south to fix the "
            "threat's southern battalion. %s screens the northern boundary and "
            "provides early warning of counterattack. The brigade engineer "
            "element breaches the obstacle belt at two lanes to open the axis.\n"
            "RESERVE: One company team, following the decisive operation, "
            "prepared to assume the mission or exploit success.\n"
            "MAIN EFFORT: %s from the breach through the seizure of %s.\n"
            "FIRES: Priority to the breach, shifting to the objective on "
            "commitment of the assault force; suppression of threat air "
            "defense along the axis.\n"
            "END STATE: %s seized, crossing site secure and intact, brigade "
            "consolidated and postured to continue east."
            % (a, g0["axis"], g0["obj"][0], b, c, a, g0["obj"][0],
               g0["obj"][0]),
            "Concentrates combat power to achieve the ratio a deliberate "
            "attack needs, at the cost of being thin in the south.",
            ["Risk: southern economy of force is exposed to counterattack"]),
        opt("Envelopment in the south — avoid the prepared defense",
            "FORM OF MANEUVER: Envelopment via the southern restricted "
            "approach.\n"
            "DECISIVE OPERATION: %s infiltrates the southern approach at "
            "night and attacks %s from the south-east, avoiding the obstacle "
            "belt entirely.\n"
            "SHAPING: %s conducts a demonstration in the north to hold the "
            "threat's attention and its reserve. %s secures the crossing site "
            "once the objective is isolated.\n"
            "RESERVE: One company team in the north, prepared to exploit if "
            "the demonstration becomes an opportunity.\n"
            "MAIN EFFORT: %s throughout.\n"
            "FIRES: Priority to the demonstration until the enveloping force "
            "is set, then shifted south. Smoke to screen the southern "
            "movement.\n"
            "END STATE: %s seized from an unexpected direction, threat "
            "obstacle belt bypassed and irrelevant, crossing site secure."
            % (a, g1["obj"][0], b, c, a, g1["obj"][0]),
            "Trades speed for surprise and avoids the strongest part of the "
            "defense. Distinguishable from COA 1 in form, direction, and "
            "risk.",
            ["Slower", "Restricted terrain limits vehicle support",
             "High payoff if surprise holds"]),
        opt("Infiltration and simultaneous attack",
            "FORM OF MANEUVER: Infiltration by multiple small elements, "
            "followed by simultaneous attack.\n"
            "DECISIVE OPERATION: Three company teams infiltrate separately "
            "during limited visibility and attack %s simultaneously from three "
            "directions at H-Hour.\n"
            "SHAPING: %s isolates the objective by fire from a support-by-fire "
            "position; the cavalry element interdicts the counterattack route.\n"
            "MAIN EFFORT: The northern infiltration element.\n"
            "FIRES: Silent until H-Hour to protect the infiltration, then "
            "massed on the objective and the counterattack route.\n"
            "END STATE: Objective seized before the threat can coordinate a "
            "response; threat reserve interdicted before it can close."
            % (g2["obj"][0], b),
            "Maximum surprise, maximum command and control difficulty. Works "
            "with well-trained subordinates and fails badly without them.",
            ["High C2 risk", "Little mutual support during infiltration"]),
        opt("Write this COA myself", "", ""),
    ][:n]


@generator("coa_screening")
def gen_screening(ctx, n=3):
    return [
        opt("COA 1 screen",
            ["COA 1", "Yes", "Yes", "Yes", "Yes", "Yes",
             "Meets all five screens."], ""),
        opt("COA 2 screen",
            ["COA 2", "Yes", "Yes", "Yes", "Yes", "Yes",
             "Distinguishable from COA 1 in form and direction."], ""),
        opt("COA 3 screen",
            ["COA 3", "Yes", "Marginal", "Yes", "Yes", "Yes",
             "Acceptability marginal — command and control risk during "
             "infiltration."], ""),
    ][:n]


@generator("task_organization")
def gen_task_org(ctx, n=8):
    subs = _subordinates(ctx)
    roles = ["Decisive operation", "Supporting effort", "Reserve",
             "Screen / reconnaissance", "Fires", "Mobility and survivability",
             "Sustainment", "Command and control"]
    rels = ["Organic", "Organic", "Organic", "Organic", "DS", "Organic",
            "DS", "Organic"]
    out = []
    for i, unit in enumerate(subs[:len(roles)]):
        out.append(opt(unit, [unit, rels[i % len(rels)], roles[i % len(roles)]],
                       ""))
    out.append(opt("Attached engineer company",
                   ["A Co, 52d BEB", "Attached", "Breach force"], ""))
    return out[:n]


# ============================================================ STEP 4 ========

@generator("wargame_method")
def gen_wargame_method(ctx, n=3):
    return [opt(name, name, "%s %s" % (desc, when))
            for _k, name, desc, when in D.WARGAME_METHODS][:n]


@generator("critical_events")
def gen_critical_events(ctx, n=10):
    t = _optype(ctx)
    if t == "defense":
        pool = ["Threat reconnaissance makes contact with the screen",
                "Screen conducts rearward passage of lines",
                "Threat preparatory fires begin",
                "Threat assault reaches the obstacle belt",
                "Threat commits second echelon",
                "Decision to commit the reserve",
                "Counterattack into the engagement area",
                "Consolidation and reorganisation",
                "Casualty evacuation under fire",
                "Resupply of Class V during contact"]
    else:
        pool = ["Forward passage of lines through the cavalry screen",
                "Crossing the line of departure",
                "Actions on contact with the threat security zone",
                "Breach of the obstacle belt",
                "Assault onto the objective",
                "Threat counterattack by the reserve",
                "Consolidation and reorganisation on the objective",
                "Seizure and securing of the crossing site",
                "Displacement of artillery forward",
                "Casualty evacuation from the objective"]
    return [opt(p, p, "") for p in pool][:n]


@generator("wargame_results")
def gen_wargame_results(ctx, n=6):
    g = _g(0)
    return [
        opt("Breach",
            ["Breach of the obstacle belt",
             "Breach force reduces two lanes under smoke; support force "
             "suppresses the far side.",
             "Threat masses artillery on the breach site within 6 minutes and "
             "commits its anti-tank reserve to the shoulder.",
             "Counter-fire engages the firing battery; the second lane is "
             "opened 200m from the first to split the threat's fires.",
             "FINDING: A single breach lane is a single point of failure. Two "
             "lanes, separated, are mandatory — this drives an additional "
             "mine-clearing line charge we do not currently hold."], ""),
        opt("Counterattack",
            ["Threat counterattack by the reserve",
             "Assault force is consolidating on the objective, at its most "
             "extended.",
             "Threat commits the tank reserve into the objective 60 to 90 "
             "minutes after we seize it.",
             "Anti-tank systems positioned on the far side during "
             "consolidation; priority of fires shifts to the counterattack "
             "route at seizure, not after contact.",
             "FINDING: The consolidation window is the vulnerable moment. "
             "Priority of fires must shift on seizure, and that shift needs a "
             "trigger, not a time."], ""),
        opt("Passage of lines",
            ["Forward passage of lines",
             "Lead battalion passes through the cavalry screen at two passage "
             "points.",
             "Threat observes the passage and fires on the passage point — it "
             "is the most predictable location on the battlefield.",
             "Passage points are widely separated, occupied for the minimum "
             "time, and covered by smoke and counter-fire.",
             "FINDING: Passage points need a hard start and end time and a "
             "battle handover line agreed in advance, or the two units fight "
             "each other's battle."], ""),
        opt("Air defense",
            ["Rotary-wing support to the assault",
             "Attack aviation is requested to support the assault.",
             "Threat short-range air defense engages at 8km.",
             "SEAD is planned against templated air defense positions; "
             "aviation ingress is routed through the masked corridor south of "
             "the ridge.",
             "FINDING: Aviation support is only available after SEAD, which "
             "requires PIR 4 to be answered before H-2."], ""),
        opt("Communications denial",
            ["Threat electromagnetic attack",
             "Brigade command net in use during the assault.",
             "Threat jams FM voice for 40 minutes and direction-finds the "
             "command post.",
             "PACE plan executed to the alternate means; command post displaces "
             "after 20 minutes of transmission.",
             "FINDING: The PACE plan must be rehearsed, not published. Every "
             "subordinate needs the jump trigger, not just the list."], ""),
        opt("Casualty evacuation",
            ["Casualty evacuation from the objective",
             "Casualties are taken during the assault.",
             "Threat indirect fire covers the objective and the obvious "
             "evacuation route.",
             "Casualty collection point sited off the obvious route; ground "
             "evacuation planned as primary with air as alternate.",
             "FINDING: Evacuation timeline exceeds the golden hour with ground "
             "evacuation alone. This is a risk the commander must accept "
             "explicitly or resource around."], ""),
    ][:n]


@generator("decision_points")
def gen_decision_points(ctx, n=6):
    g = _g(0)
    return [
        opt("Commit the reserve",
            ["DP 1", "Commit the reserve to exploit or to reinforce",
             "On seizure of the objective, or on loss of 30% combat power in "
             "the decisive operation, whichever is first",
             "PIR 1 (threat reserve commitment)"], ""),
        opt("Number of breach lanes",
            ["DP 2", "Open a second breach lane",
             "NLT H-1, based on obstacle belt composition",
             "PIR 2 (obstacle belt)"], ""),
        opt("Shift priority of fires",
            ["DP 3", "Shift priority of fires from the breach to the objective",
             "On commitment of the assault force", "—"], ""),
        opt("Crossing site seizure",
            ["DP 4", "Commit the crossing-site force early",
             "On confirmation the bridge is prepared for demolition",
             "PIR 3 (bridge status)"], ""),
        opt("Aviation employment",
            ["DP 5", "Employ rotary-wing support",
             "NLT H-2, based on air defense picture and weather",
             "PIR 4 (air defense laydown)"], ""),
        opt("Alternate supply route",
            ["DP 6", "Activate the alternate main supply route",
             "On closure of the primary route by civilian movement or "
             "interdiction", "PIR 8 (population movement)"], ""),
    ][:n]


@generator("sync_matrix")
def gen_sync(ctx, n=6):
    phases = _phases(ctx)
    rows = [
        [phases[0],
         "Units complete pre-combat checks in assembly areas",
         "Cavalry screens; UAS confirms threat forward positions",
         "Targets refined; counter-fire radar zones established",
         "Combat loads topped off; ambulances forward",
         "Camouflage and dispersion in assembly areas; CBRN posture set",
         "Rehearsals complete; PACE plan confirmed with all stations"],
        [phases[1] if len(phases) > 1 else "Phase II",
         "Forward passage of lines; movement to the line of departure",
         "Collection focused on NAI 1 to answer PIR 1",
         "Preparatory fires on templated positions; SEAD as required",
         "Logistics package follows at 5km",
         "Air defense posture assumed; route clearance forward",
         "Command post forward displaces; net control established"],
        [phases[2] if len(phases) > 2 else "Phase III",
         "Breach and assault; reserve follows the decisive operation",
         "UAS observes the counterattack route; PIR 1 answered",
         "Priority of fires to the breach then the objective; smoke on the "
         "flank",
         "Casualty collection point established forward; ambulance exchange "
         "point set",
         "Obscuration on the breach; counter-fire responsive",
         "Commander forward with the decisive operation; DP 1 assessed"],
        [phases[3] if len(phases) > 3 else "Phase IV",
         "Consolidate and reorganise; anti-tank systems oriented on the "
         "counterattack route",
         "Collection shifts to threat reconstitution",
         "Priority of fires to the counterattack route",
         "Resupply of Class III and V; casualty evacuation completed",
         "Survivability positions begun; CBRN monitoring",
         "Command post displaces forward; reports rendered"],
    ]
    return [opt(r[0], r, "") for r in rows][:n]


@generator("risk_register")
def gen_risk(ctx, n=8):
    def row(h, p, s, c, r):
        return [h, p, s, D.risk_level(s, p), c, r]
    return [
        opt("Counter-fire on the breach",
            row("Threat counter-fire strikes the breach site", "Likely",
                "Critical",
                "Two separated lanes; smoke; counter-fire radar zones; "
                "displacement after each mission", "Moderate"), ""),
        opt("Counterattack during consolidation",
            row("Threat armoured counterattack during consolidation",
                "Likely", "Critical",
                "Anti-tank systems positioned on seizure; priority of fires "
                "shifts at seizure; reserve positioned to reinforce",
                "Moderate"), ""),
        opt("Civilian casualties",
            row("Civilian casualties in the district centre", "Occasional",
                "Catastrophic",
                "Restrictive fire control measures on the built-up area; "
                "positive identification required; approval authority held at "
                "brigade", "Moderate"), ""),
        opt("Communications denial",
            row("Loss of command net to electromagnetic attack", "Likely",
                "Moderate",
                "Rehearsed PACE plan; pre-briefed contingency actions; command "
                "post displacement after 20 minutes of transmission", "Low"),
            ""),
        opt("Fratricide at the boundary",
            row("Fratricide at the boundary with the adjacent unit",
                "Occasional", "Catastrophic",
                "Coordinated fire control measures; liaison exchanged; "
                "restrictive fire line on the boundary; recognition signals "
                "briefed", "Moderate"), ""),
        opt("Casualty evacuation exceeds capacity",
            row("Casualty evacuation exceeds capacity on the objective",
                "Occasional", "Critical",
                "Forward casualty collection point; non-standard evacuation "
                "platforms identified; air evacuation requested at H-1",
                "Moderate"), ""),
        opt("Sustainment interdiction",
            row("Interdiction of the main supply route", "Likely", "Moderate",
                "Alternate route reconnoitred and cleared; convoy security; "
                "route status reported every 6 hours", "Low"), ""),
        opt("Weather grounds aviation",
            row("Weather prevents rotary-wing support", "Occasional",
                "Moderate",
                "Ground casualty evacuation as primary; fires plan does not "
                "depend on aviation", "Low"), ""),
    ][:n]


# ============================================================ STEP 5 ========

@generator("criteria_weights")
def gen_weights(ctx, n=8):
    chosen = ctx.get("eval_criteria")
    if isinstance(chosen, list) and chosen:
        names = [str(c) for c in chosen]
    else:
        names = [name for _k, name, _d in D.EVALUATION_CRITERIA_LIBRARY[:5]]
    weights = ["3 (highest)", "3 (highest)", "2", "2", "1", "1", "1", "1"]
    why = ["The commander's guidance made this the deciding factor.",
           "Directly tied to the stated end state.",
           "Important but not decisive on this mission.",
           "Matters mainly for the follow-on operation.",
           "Included for completeness; unlikely to separate the COAs.",
           "Secondary consideration.", "Secondary consideration.",
           "Secondary consideration."]
    return [opt(nm, [nm, weights[i % len(weights)], why[i % len(why)]], "")
            for i, nm in enumerate(names)][:n]


@generator("decision_matrix")
def gen_matrix(ctx, n=8):
    chosen = ctx.get("eval_criteria")
    if isinstance(chosen, list) and chosen:
        names = [str(c) for c in chosen]
    else:
        names = [name for _k, name, _d in D.EVALUATION_CRITERIA_LIBRARY[:5]]
    scores = [["1", "2", "3"], ["2", "1", "3"], ["1", "3", "2"],
              ["2", "1", "3"], ["1", "2", "3"], ["3", "1", "2"],
              ["2", "3", "1"], ["1", "2", "3"]]
    weights = ["3", "3", "2", "2", "1", "1", "1", "1"]
    out = []
    for i, nm in enumerate(names):
        s = scores[i % len(scores)]
        out.append(opt(nm, [nm, weights[i % len(weights)], s[0], s[1], s[2]],
                       "Ranked 1 = best. Multiply by weight and total the "
                       "columns; lowest weighted total wins."))
    return out[:n]


@generator("coa_advantages")
def gen_adv(ctx, n=3):
    return [
        opt("COA 1",
            ["COA 1",
             "Concentrates combat power at the point of penetration; simplest "
             "to command; fastest to the objective; best supported by fires.",
             "Southern economy of force is exposed; predictable — it is the "
             "approach the threat has templated; depends on a successful "
             "breach.",
             "Moderate risk to force, low risk to mission."], ""),
        opt("COA 2",
            ["COA 2",
             "Avoids the obstacle belt and the strongest part of the defense; "
             "achieves surprise; attacks from an unexpected direction.",
             "Slower; restricted terrain limits vehicle support and casualty "
             "evacuation; surprise is perishable and may be lost during "
             "movement.",
             "Low risk to force if surprise holds, high risk to mission if it "
             "does not."], ""),
        opt("COA 3",
            ["COA 3",
             "Maximum surprise; overwhelms the threat's decision cycle; "
             "hardest for the threat to counter.",
             "Very high command and control burden; little mutual support "
             "during infiltration; a single compromised element unravels the "
             "whole scheme.",
             "High risk to force, high risk to mission — viable only with "
             "well-trained subordinates."], ""),
    ][:n]


@generator("staff_recommendation")
def gen_rec(ctx, n=3):
    return [
        opt("Recommend COA 1",
            "The staff recommends COA 1. It scores best against mission "
            "accomplishment and sustainment feasibility, the two criteria the "
            "commander weighted highest, and it is the only COA whose concept "
            "of support can be executed with the transportation assets on "
            "hand. Its principal weakness — predictability — is mitigated by "
            "the demonstration in the south and by the deception effort. The "
            "commander is accepting moderate risk to the force at the breach "
            "site and low risk to the mission overall.",
            "States the recommendation, the deciding criteria, the mitigation, "
            "and the risk being accepted."),
        opt("Recommend COA 2",
            "The staff recommends COA 2. While COA 1 is faster and simpler, "
            "the war game showed that the breach is a single point of failure "
            "we cannot adequately resource — we are one mine-clearing line "
            "charge short of a two-lane breach. COA 2 avoids the obstacle belt "
            "entirely and therefore removes the failure mode rather than "
            "mitigating it. The cost is tempo and a dependence on surprise; "
            "the commander is accepting high risk to the mission in exchange "
            "for low risk to the force.",
            "Recommends against the obvious choice on the strength of a "
            "war-game finding — which is what the war game is for."),
        opt("Write the recommendation myself", "", ""),
    ][:n]


# ============================================================ STEP 6 ========

@generator("approved_coa")
def gen_approved(ctx, n=4):
    return [
        opt("COA 1 as briefed", "COA 1, approved as briefed.", ""),
        opt("COA 1 with modifications",
            "COA 1, approved with modifications directed by the commander.",
            "The most common real outcome."),
        opt("COA 2 as briefed", "COA 2, approved as briefed.", ""),
        opt("COA 2 with modifications",
            "COA 2, approved with modifications directed by the commander.",
            ""),
    ][:n]


@generator("coa_modifications")
def gen_mods(ctx, n=6):
    return [
        opt("Second breach lane is mandatory",
            "The second breach lane is not optional. Resource it from division "
            "or change the scheme.", ""),
        opt("Reserve moves forward",
            "Position the reserve one terrain feature further forward to cut "
            "commitment time to under 30 minutes.", ""),
        opt("Priority of fires shifts on trigger, not time",
            "Priority of fires shifts to the counterattack route on seizure of "
            "the objective — on the trigger, not at a fixed time.", ""),
        opt("Add a deception effort in the south",
            "Add a demonstration in the south to hold the threat's reserve for "
            "the first two hours.", ""),
        opt("Casualty evacuation resourced forward",
            "Push a second ambulance exchange point forward; I am not "
            "accepting the evacuation timeline as briefed.", ""),
        opt("Rehearse the PACE plan",
            "The PACE plan will be rehearsed, not briefed. Every station "
            "demonstrates the jump before the combined arms rehearsal.", ""),
    ][:n]


@generator("final_guidance")
def gen_final_guidance(ctx, n=3):
    return [
        opt("Standard final guidance",
            "Publish the order NLT H-24. I want the combined arms rehearsal at "
            "H-12 with all company commanders and the fire support officers "
            "present — not their representatives. My CCIRs stand as refined. I "
            "am accepting moderate risk to the force at the breach and low "
            "risk to the mission. If PIR 1 is not answered by H-6, brief me "
            "before the rehearsal; I may adjust the reserve's positioning. "
            "Subordinate confirmation briefs are due to the executive officer "
            "within two hours of the order.",
            "Covers publication, rehearsal, risk, and the branch trigger."),
        opt("Compressed final guidance",
            "Publish a fragmentary order now and the full order by H-12. "
            "Confirmation briefs by radio within one hour. Rehearsal is a "
            "map rehearsal at H-6, not terrain. I accept the increased risk "
            "that comes with the shorter preparation.",
            "For a compressed timeline; note the explicit risk statement.",
            ["Accepting reduced rehearsal quality"]),
        opt("Write the final guidance myself", "", ""),
    ][:n]


@generator("rehearsals")
def gen_rehearsals(ctx, n=6):
    return [
        opt("Confirmation brief",
            "Confirmation brief: subordinate commanders back-brief the "
            "executive officer within 2 hours of receiving the order. "
            "Standard: task, purpose, and their part in the concept.", ""),
        opt("Combined arms rehearsal",
            "Combined arms rehearsal at H-12, terrain model, all company "
            "commanders, fire support officers, and the support operations "
            "officer present. Standard: execution walked phase by phase "
            "against the enemy MLCOA.", ""),
        opt("Support rehearsal",
            "Sustainment rehearsal at H-14, run by the support operations "
            "officer, covering resupply timing, casualty evacuation, and "
            "recovery.", ""),
        opt("Fires rehearsal",
            "Fires rehearsal at H-16, covering the target list, triggers, "
            "clearance of fires, and the counter-fire fight.", ""),
        opt("Battle drill rehearsal",
            "Battle drill rehearsals at company level: actions on contact, "
            "breach drill, and consolidation on the objective. Executed "
            "continuously until H-4.", ""),
        opt("Communications rehearsal",
            "Communications rehearsal at H-18: every station demonstrates the "
            "PACE jump, including the degraded and emergency means.", ""),
    ][:n]


# ============================================================ STEP 7 ========

@generator("references")
def gen_refs(ctx, n=6):
    return [
        opt("Higher order",
            "Operation Order 24-01, %s, dated 010001Z."
            % _higher_echelon(ctx)[0], ""),
        opt("Map sheet",
            "Map: Series V795, Sheet 3842 III, Edition 4, 1:50,000.", ""),
        opt("Datum", "Datum: WGS-84.", ""),
        opt("Doctrinal reference", "FM 6-0, Commander and Staff Organization "
            "and Operations.", ""),
        opt("Standard operating procedure",
            "Unit Tactical Standard Operating Procedure, current edition.", ""),
        opt("Rules of engagement",
            "Rules of engagement as promulgated by higher headquarters.", ""),
    ][:n]


@generator("time_zone")
def gen_tz(ctx, n=4):
    return [
        opt("Zulu (Z)", "ZULU (Z)",
            "Standard for multinational and joint operations — removes local "
            "time confusion entirely."),
        opt("Local", "LOCAL",
            "Simpler for a single-nation force operating in one time zone."),
        opt("Delta (D)", "DELTA (D)", ""),
        opt("Charlie (C)", "CHARLIE (C)", ""),
    ][:n]


@generator("concept_of_operations")
def gen_concept(ctx, n=3):
    approved = ctx.get("approved_coa") or ""
    coa = ctx.get("coa_1") if "1" in str(approved) else ctx.get("coa_2")
    coa = coa or ctx.get("coa_1") or ""
    phases = _phases(ctx)
    lead = ("This operation is conducted in %d phases.\n\n" % len(phases))
    body = "\n".join("%s: %s" % (p, d) for p, d in zip(
        phases,
        ["Units complete preparation, rehearsals, and pre-combat checks in "
         "assembly areas.",
         "The force conducts a forward passage of lines and moves to the line "
         "of departure.",
         "The decisive operation is executed; shaping operations fix and "
         "isolate.",
         "The force consolidates, reorganises, and defeats the expected "
         "counterattack.",
         "The force transitions to follow-on operations on order."]))
    if coa:
        return [
            opt("Built from the approved COA",
                str(coa) + "\n\n" + lead + body,
                "Assembled from the COA you approved plus a phase structure. "
                "Edit freely — this is a draft, not a decision."),
            opt("Phased structure only",
                lead + body,
                "Use when you would rather write the concept from scratch but "
                "want the phase skeleton."),
            opt("Write the concept myself", "", ""),
        ][:n]
    return [opt("Phased structure", lead + body, ""),
            opt("Write the concept myself", "", "")][:n]


@generator("tasks_to_subordinates")
def gen_tasks_sub(ctx, n=8):
    subs = _subordinates(ctx)
    t = _optype(ctx)
    g = _g(0)
    if t == "defense":
        pairs = [
            ("Defend %s" % g["bp"], "to defeat the threat's main attack in %s"
             % g["ea"], "Main effort"),
            ("Defend in the southern sector",
             "to deny the threat access to the boundary", "Supporting effort"),
            ("Screen forward of %s" % g["pl"][0],
             "to provide early warning and force early deployment",
             "Supporting effort"),
            ("Be prepared to counterattack into %s" % g["ea"],
             "to destroy the penetrating threat element", "Reserve"),
            ("Provide priority of fires to the main effort",
             "to defeat the assault forward of the obstacle belt", "DS"),
            ("Emplace the obstacle belt along the canal line",
             "to turn the threat into %s" % g["ea"], "Supporting effort"),
            ("Establish the brigade support area",
             "to sustain the defense through 96 hours", "Supporting"),
        ]
    else:
        pairs = [
            ("Attack along %s to seize %s" % (g["axis"], g["obj"][0]),
             "to enable the division's exploitation east", "Main effort"),
            ("Conduct a supporting attack in the south",
             "to fix the threat's southern battalion", "Supporting effort"),
            ("Screen the northern boundary",
             "to provide early warning of counterattack", "Supporting effort"),
            ("Follow the main effort; be prepared to assume the mission",
             "to maintain the tempo of the attack", "Reserve"),
            ("Provide priority of fires to the breach, then the objective",
             "to enable the assault", "DS"),
            ("Breach the obstacle belt at two lanes",
             "to open the axis for the main body", "Supporting effort"),
            ("Establish the brigade support area forward",
             "to sustain the attack through consolidation", "Supporting"),
        ]
    out = []
    for i, (task, purpose, pri) in enumerate(pairs):
        unit = subs[i] if i < len(subs) else "TBD"
        out.append(opt(unit, [unit, task, purpose, pri], ""))
    return out[:n]


def _scheme(title, text, alt=None):
    out = [opt("Drafted from the plan", text,
               "Assembled from decisions you already made. Edit to taste.")]
    if alt:
        out.append(opt("Alternative emphasis", alt, ""))
    out.append(opt("Write %s myself" % title, "", ""))
    return out


@generator("scheme_maneuver")
def gen_scheme_man(ctx, n=3):
    g = _g(0)
    return _scheme(
        "the scheme of maneuver",
        "The brigade attacks with two battalions forward and one following. "
        "The decisive operation attacks along %s, breaches the obstacle belt "
        "at two lanes, and seizes %s. The supporting effort attacks in the "
        "south to fix the threat's southern battalion and prevent its "
        "repositioning. The cavalry squadron screens the northern boundary and "
        "provides early warning of counterattack from the north-east. The "
        "reserve follows the decisive operation at one terrain feature and is "
        "prepared to assume the mission, exploit success toward the crossing "
        "site, or block a counterattack. On seizure of %s the brigade "
        "consolidates, orients anti-tank systems on the counterattack route, "
        "and prepares to continue the attack east on order."
        % (g["axis"], g["obj"][0], g["obj"][0]))[:n]


@generator("scheme_intelligence")
def gen_scheme_int(ctx, n=3):
    g = _g(0)
    return _scheme(
        "the scheme of intelligence",
        "Information collection is focused on answering PIR 1 (threat reserve "
        "commitment) before the decision point at seizure of the objective. "
        "The cavalry squadron observes %s continuously from H-6. Brigade "
        "unmanned aerial systems cover %s during daylight and shift to the "
        "counterattack route at H-Hour. The military intelligence company "
        "provides signals collection oriented on the threat's command net and "
        "counter-battery radar. All units report threat contact by size, "
        "activity, location, unit, time, and equipment on the operations net "
        "immediately, and submit a consolidated report every six hours. "
        "Reporting on PIR 1 goes directly to the brigade commander without "
        "passing through the normal reporting chain."
        % (g["nai"], g["tai"]))[:n]


@generator("scheme_fires")
def gen_scheme_fires(ctx, n=3):
    g = _g(0)
    return _scheme(
        "the scheme of fires",
        "Priority of fires is to the decisive operation throughout. Fires "
        "support the operation in three parts. First, suppression of threat "
        "air defense along the axis to enable rotary-wing support. Second, "
        "suppression and obscuration at the breach site, planned as a group "
        "with a trigger tied to the breach force crossing the last covered "
        "position — not to a clock time. Third, on seizure of %s, priority "
        "shifts to the counterattack route and the pre-planned targets covering "
        "it. Counter-fire is responsive throughout; firing batteries displace "
        "after each mission. A restrictive fire area is established over the "
        "district centre and the hospital; fires into it require brigade "
        "approval. Clearance of fires across the northern boundary is "
        "coordinated through the liaison officer prior to H-Hour."
        % g["obj"][0])[:n]


@generator("scheme_protection")
def gen_scheme_prot(ctx, n=3):
    return _scheme(
        "the scheme of protection",
        "Protection priorities are the breach force, the command posts, and the "
        "brigade support area, in that order. Assume persistent threat aerial "
        "observation: units disperse in assembly areas, camouflage against "
        "thermal and visual observation, and enforce emissions discipline. "
        "Command posts displace after no more than twenty minutes of "
        "continuous transmission. Air defense assets protect the support area "
        "and the artillery firing positions. CBRN posture is MOPP 0 with masks "
        "carried; automatic masking on any indication. Survivability effort "
        "prioritises the artillery firing positions, then the support area. "
        "Personnel recovery is planned for the objective area with a "
        "designated recovery force from the reserve. Route clearance precedes "
        "sustainment movement on the main supply route.")[:n]


@generator("sustainment_concept")
def gen_sustainment(ctx, n=3):
    return _scheme(
        "the concept of support",
        "The brigade support battalion establishes the brigade support area "
        "8 kilometres behind the line of departure and displaces forward once "
        "the objective is seized. Priority of support is to the decisive "
        "operation throughout, shifting to the reserve on its commitment.\n\n"
        "LOGISTICS: Units cross the line of departure with full combat loads "
        "plus one. One logistics package moves forward per 24 hours, timed to "
        "arrive during consolidation rather than during the assault. "
        "Maintenance collection points are established behind each maneuver "
        "battalion; recovery is unit responsibility to the collection point "
        "and brigade responsibility beyond it.\n\n"
        "PERSONNEL: Strength reporting at 0600 and 1800. Casualty reports are "
        "submitted immediately by the fastest means. Replacements flow through "
        "the support area.\n\n"
        "HEALTH SERVICE SUPPORT: Role 1 treatment is at each battalion aid "
        "station; Role 2 is in the brigade support area. Casualty collection "
        "points are established forward of the objective and off the obvious "
        "evacuation route. Ground evacuation is primary; air evacuation is "
        "alternate and weather-dependent. Ambulance exchange points are "
        "established at the passage points.")[:n]


@generator("command_posts")
def gen_cps(ctx, n=3):
    return _scheme(
        "the command post plan",
        "The tactical command post is forward with the decisive operation and "
        "displaces on order after seizure of the objective. The main command "
        "post is 12 kilometres behind the line of departure and does not "
        "displace during the operation. The support area command post is "
        "co-located with the brigade support area.\n\n"
        "REPORTS: Situation reports at 0600 and 1800. Combat power reports at "
        "0600 and 1800. Immediate reports for any CCIR, contact with a threat "
        "element of platoon size or larger, any civilian casualty, and any "
        "commitment of the reserve.")[:n]


@generator("succession")
def gen_succession(ctx, n=3):
    return _scheme(
        "succession of command",
        "Succession of command is: the brigade commander, the deputy commanding "
        "officer, the executive officer, then the commander of the battalion "
        "designated as the main effort. Succession is announced on the "
        "operations net and confirmed by the next higher headquarters.")[:n]


@generator("pace_plan")
def gen_pace(ctx, n=6):
    return [
        opt("Brigade command net",
            ["Brigade command net", "FM voice (secure)", "Tactical satellite",
             "Data / chat over the tactical network", "Messenger"], ""),
        opt("Brigade operations and intelligence net",
            ["Brigade O&I net", "FM voice (secure)",
             "Data / chat over the tactical network", "Tactical satellite",
             "Liaison officer in person"], ""),
        opt("Fires net",
            ["Fires net", "Digital fire control system", "FM voice (secure)",
             "Tactical satellite", "Pre-planned targets on trigger"], ""),
        opt("Sustainment net",
            ["Sustainment net", "Data / chat", "FM voice",
             "Cellular / commercial where available", "Convoy commander in "
             "person"], ""),
        opt("Higher headquarters",
            ["To higher headquarters", "Tactical satellite", "Data / chat",
             "FM voice via retransmission", "Liaison officer"], ""),
        opt("Casualty evacuation",
            ["Casualty evacuation", "FM voice on the medical net",
             "Brigade command net", "Any station relay",
             "Physical delivery to the ambulance exchange point"], ""),
    ][:n]


# ---------------------------------------------------------------- dispatch --

def generate(gen_key, ctx, n=6):
    """Return candidate options for a generator key, or a safe fallback."""
    fn = REGISTRY.get(gen_key)
    if fn is None:
        return [opt("Write it yourself", "",
                    "No offline template is defined for this field yet — "
                    "write what you need, or configure a model provider for "
                    "generated options.")]
    try:
        out = fn(ctx, n) or []
    except Exception as exc:  # a broken template must never block the staff
        return [opt("Write it yourself", "",
                    "Template error (%s). Write what you need." % exc)]
    for i, o in enumerate(out):
        o.setdefault("flags", [])
        o["id"] = "off-%s-%d" % (gen_key, i)
        o["provider"] = "offline"
    return out
