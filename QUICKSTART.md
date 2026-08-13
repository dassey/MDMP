# Quick start

Written for someone who has never run the military decision-making process.
You do not need to know it. The tool explains each step in plain English as you
reach it, and offers you real options instead of a blank page.

---

## 1. Start it

```bash
cd mdmp
python3 serve.py
```

It prints something like:

```
  Open on this machine:   http://localhost:8080
  Others on the network:  http://10.1.20.14:8080
```

Open the first address in a browser. Create the administrator account — that is
you.

## 2. Add the other people

**Settings → Accounts → Add an account.** Give each person a username, a
password, a role, and their staff section.

They open the *second* address (the one with the IP) from their own laptop, on
the same network, and sign in. Nothing gets installed on their machine.

## 3. Start a plan

Name it — `OPERATION IRON ANVIL`, or whatever the exercise calls it — and press
**Start a new plan**.

## 4. Work down the seven steps

The rail on the left is the process. You are on step 1.

For each field:

- Read the plain-English line under the heading. It says what the field is for.
- Press **Generate options**.
- You get several concrete answers, each with a note explaining why you would
  pick it and what it costs you.
- Press **Use this** to take one, **Use & edit** to take one and change it, or
  **Write my own** to ignore them all.
- **More options** gives you a different set.

Some fields build a list (press *Add to list* on several options). Some build a
table (edit the cells directly, or add your own rows).

You can jump to any step at any time by clicking it in the rail. If you change
something early after answering things later, the tool marks the later answers
**needs review** and tells you which ones — it does not throw your work away.

At the end of steps 1, 2, and 6 there is a button to generate a **warning
order**. Issue them. They are what let subordinate units start working while you
are still planning.

## 5. Move to staff production

When the steps are done, press **Move to staff production**.

The tool writes the whole five-paragraph order from what you decided. Every
paragraph already has a draft. Open the **Staff production** tab and you will see
each paragraph with a suggested owner — S-2 owns the enemy paragraph, S-4 owns
sustainment, and so on.

Now the other people matter. Each person:

1. Opens the plan.
2. Finds their paragraphs under **Assigned to you**, or presses **Claim** on one.
3. Edits the draft.
4. Sets the status to **ready for review**.

The commander (or an admin) sets a paragraph to **approved**. Nobody else can.

## 6. Get the order out

The **OPORD** tab shows the whole order. Export it as:

- **Print / HTML** — for printing or reading
- **Word** — a `.docx` anyone can edit
- **Markdown** or **Plain text** — for pasting anywhere
- **Plan data** — the full JSON, if you want to do something else with it

---

## The seven steps, in one line each

1. **Receipt of Mission** — Who are you, what kind of fight, how long do you have.
2. **Mission Analysis** — What were you told to do, what must you do that nobody
   said, what do you know, what are you guessing, what will the enemy and the
   ground do about it. *The long one. It decides whether the rest is any good.*
3. **COA Development** — Genuinely different ways to do the job.
4. **COA Analysis** — Fight each one against a thinking enemy, on paper. Find
   what breaks.
5. **COA Comparison** — Score them against criteria you chose *before* you had
   the plans, so the comparison is honest.
6. **COA Approval** — The commander picks one and sharpens the intent.
7. **Orders Production** — Turn it into an order people can execute.

---

## Making the options better

Out of the box the options come from built-in doctrinal templates. They read
your plan and adapt to it, and they work with no network at all.

If the laptop has a local model, point the tool at it — **Settings → Model
provider** — and the options will fit your specific scenario much more closely.
Ollama with a 7B instruct model is the easiest path and runs comfortably on a
normal laptop.

If the laptop has internet and you want the strongest drafting, install the
Claude client (`pip install anthropic`), choose that provider, and paste an API
key.

## Making the doctrine better

Drop your publications — FM 5-0, FM 6-0, ADP 5-0, whatever your unit uses — into
the `corpus/` folder as PDFs, then **Settings → Doctrine library → Index new
documents**. The tool will pull the relevant passages into option generation and
show you which document each one came from.

## If something goes wrong

- **Nobody else can reach it.** They need the IP address, not `localhost`, and
  they must be on the same network. A host firewall may need to allow the port.
- **A PDF indexed as empty.** It is probably a scan. Run OCR on it, or
  `pip install pypdf` if it is a generated PDF.
- **You want to start over.** Stop the server and delete `data/mdmp.db`.
