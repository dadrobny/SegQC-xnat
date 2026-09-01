## 7. Verify on a platform this loop never runs on

Test hygiene reduces the odds; it does not close the gap. **No role in this loop
sees a non-Linux checkout, a different working directory, or real CI status**,
so the honest response is to look at the one gate that does:

- Once work is pushed, **check the real CI result** rather than inferring it
  from a green local suite. Report what CI actually said, including "no CI is
  configured here" or "it had not finished" — never let a local pass stand in
  for a platform the loop cannot reach.
- When CI is red on a leg that passed locally, treat it as a **portability
  finding first** (§6), not a flake, until the log says otherwise. Every
  recorded instance looked like a content problem and was a platform one.
