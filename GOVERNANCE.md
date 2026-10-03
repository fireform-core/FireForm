# FireForm Governance

This document describes how the FireForm project is governed: who does what, how decisions are made, and how contributors can grow within the community.

## Roles

FireForm uses three roles. They are intentionally simple.

### Owners

**Organization administrators — set direction, own accountability.**

- Set the project's strategic direction and governance.
- Manage organization settings, repositories, teams, and permissions.
- Make major architectural and strategic decisions.
- Appoint and remove Maintainers.
- Oversee security and project sustainability.

**GitHub permission:** Organization Owner (full administrative access).

> Every Owner holds the GitHub *Organization Owner* role and therefore has full administrative access. Keep at least two active Owners at all times for continuity.

---

### Maintainers

**Technical leadership — keep the codebase healthy.**

- Review and merge pull requests.
- Maintain code quality, tests, and releases.
- Manage issues and support contributors.
- Lead particular repositories or technical areas.
- Participate in technical planning.

**GitHub permission:** `Maintain` or `Write`, depending on repository responsibilities.

---

### Contributors

**Community participation — anyone who helps FireForm improve.**

- Contribute code, documentation, tests, and designs.
- Report bugs and suggest features.
- Participate in discussions and testing.
- Earn recognition and a path to become Maintainers.

**GitHub permission:** Public contributors submit pull requests from forks without joining the organization. Additional access is granted only when specifically needed.

---

## Permission Matrix

| Action | Owner | Maintainer | Contributor |
| :--- | :---: | :---: | :---: |
| Manage organization settings | ✅ | ❌ | ❌ |
| Manage repository access | ✅ | Generally ❌ | ❌ |
| Review pull requests | ✅ | ✅ | Can participate |
| Merge pull requests | ✅ *(subject to rules)* | ✅ *(subject to rules)* | ❌ |
| Manage releases | ✅ | If authorized | ❌ |
| Submit pull requests | ✅ | ✅ | ✅ |
| Participate in discussions | ✅ | ✅ | ✅ |

> Branch protection rules and required CI checks apply to everyone, including Owners.

---

## Current Maintainers

| Name | GitHub | Area |
| :--- | :--- | :--- |
| Marc Vergés Santiago | [@marcvergees](https://github.com/marcvergees) | Core backend, architecture |
| Vincent Harkins | [@vharkins1](https://github.com/vharkins1) | Core backend, infrastructure |

---

## Promotion Path

The hierarchy is simple, but promotion criteria should be explicit.

**Contributor → Maintainer**
Sustained, high-quality contributions; good collaboration; demonstrated responsibility and reliability over time. Nominated by an existing Maintainer and approved by the Owners.

**Maintainer → Owner**
Long-term trust, commitment to the project's future, and unanimous agreement from existing Owners.

A person's role reflects their responsibilities. GitHub permissions should provide only the access appropriate to those responsibilities — with the exception that every Owner receives full organization administration by design.

---

## Decision Making

- **Day-to-day decisions** (code review, issue triage): Maintainers.
- **Technical direction** (architecture, major dependencies, releases): Maintainers with Owner visibility.
- **Governance and strategic decisions** (role changes, forks, project future): Owners.

For significant decisions, open a [GitHub Discussion](https://github.com/fireform-core/FireForm/discussions) so the community can participate before a conclusion is reached.

---

## Questions?

Open a [Discussion](https://github.com/fireform-core/FireForm/discussions) or reach out on [Discord](https://discord.gg/nBv5b6kF68).
