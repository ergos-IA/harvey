"""Collectors for selling to Spanish mid-sized companies, account by account.

Account-based, not map-based: a few dozen hand-picked accounts per batch
("lote") come in through ``harvey accounts import``, and these collectors
read Spain-specific buying signals for exactly those accounts:

- ``accounts``  — CSV import of the hand-picked accounts and their firmographics
- ``web``       — what the homepage already fetched by PROFILE says (languages,
                  export claims, helpdesk, e-commerce, B2B portal, ERP mentions)
- ``ats_es``    — job boards Spanish companies use (Personio, Teamtailor,
                  Factorial, JOIN, SmartRecruiters), found only from their site
- ``infojobs``  — the official InfoJobs API, when credentials are configured
- ``jobs``      — open roles in the functions the offer is built for
- ``borme``     — acts registered in the BORME (BOE open data)
- ``news``      — Spanish press headlines (Google News RSS)

Every fact is an observation with confidence and provenance, like the rest of
Harvey, and only CONFIRMED signals are collected. Everything fetched from
outside is untrusted text: it is cleaned and capped before it is stored, and
fenced (harvey.untrusted) whenever it reaches a prompt.
"""
