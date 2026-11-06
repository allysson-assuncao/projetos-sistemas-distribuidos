# HANDOFF: Smart Contract Development & Planning — AP8 (Distributed Systems)

## 1. Project Overview & Executive Brief

* **Course Unit:** Distributed Systems — Practical Activity 8 (AP8: Smart Contracts & Local Integration).
* **Reference Document:** [`Conteúdo e Enunciado Atividade Prática 8 - SD.pdf`](./Conteúdo%20e%20Enunciado%20Atividade%20Prática%208%20-%20SD.pdf)
* **Working Directory:** `atividade_pratica8`
* **Core Philosophy & Working Constraints:**
  * **Efficiency First:** Deliver the *minimum necessary and sufficient* implementation to score 100% against the rubric.
  * **Zero Over-engineering:** The activity is not evaluated with extreme academic rigor. Keep lines of code minimal, readable, and free from unnecessary third-party abstractions.
  * **Speed & Low Friction:** Minimize human intervention and execution time. Everything must be deterministic and testable via standard CLI tools.

---

## 2. Selected Theme: Document / Certificate Registry (`DocumentRegistry.sol`)

The user explicitly selected the **Document/Certificate Registry** theme after evaluating alternatives (Vault, Voting, etc.).

### Why this Theme Fits the Constraints:
1. **No Token / Ether Handling:** Avoids `payable` functions, ETH balance tracking, and financial transfer vulnerabilities.
2. **Natural Architectural Alignment:** Directly exemplifies the core distributed systems question: *"What belongs on-chain vs. off-chain?"* (Only cryptographic hashes live on-chain; original documents remain off-chain).
3. **Concise & Robust:** Can be implemented in ~35-45 lines of clean Solidity with straightforward test cases.

### Mandatory Technical Specifications:
* **State-Changing Function 1:** `registerDocument(bytes32 docHash)` — stores timestamp, registrar address, and sets status to active. Emits event.
* **State-Changing Function 2:** `revokeDocument(bytes32 docHash)` — alters document validity to revoked. Restricted to the contract owner/issuer via validation. Emits event.
* **View Function (Read):** `verifyDocument(bytes32 docHash)` — returns existence, validity, timestamp, and registrar address without gas cost for off-chain callers.
* **Event:** `DocumentRegistered(bytes32 indexed docHash, address indexed registrant, uint256 timestamp)`.
* **Validation / Revert Rules:**
  * `require(!documents[docHash].exists, "Document already registered")`
  * `require(msg.sender == owner, "Caller is not the owner")`
* **Automated Test Suite (Minimum 4 tests):**
  1. Successful document registration and state persistence.
  2. Event emission verification on registration.
  3. Successful document revocation by the authorized owner.
  4. Expected `revert` on unauthorized revocation or duplicate registration attempt.

### Mandatory Course Deliverables:
1. Smart contract source code (`.sol`) and automated test scripts.
2. Execution commands for compilation, testing, and local node deployment.
3. Laboratory evidence: deployed contract address, transaction hashes, captured terminal logs, and emitted events.
4. Technical Analysis Report answering:
   * Analysis of at least 3 security risks (e.g., Access Control failures, Front-running / Hash Collision, Storage exhaustion / Gas DoS).
   * Architectural comparison: On-chain smart contract vs. traditional REST API service.
   * Direct answers to the 5 theoretical analysis questions from page 12 of the assignment PDF.

---

## 3. Mission for the Incoming Robust Agent

You are an expert distributed systems and smart contract architect. Your objective is to take this handoff, conduct a focused alignment session with the user, and generate a single, definitive, self-sufficient **`IMPLEMENTATION_PLAN.md`** in the project root.

### Workflow Directives:
1. **Direct Autonomous Context Ingestion:**
   * Review this handoff document and understand the selected theme and constraints.
   * Understand that the user wants minimal effort, high speed, and complete adherence to requirements.
2. **Interactive `/grill-me` Alignment:**
   * Run an interactive Q&A session with the user using the `ask_question` tool.
   * Address open design choices one at a time (e.g., confirming the framework — Hardhat recommended —, directory structure, and reporting format). Always propose a clear `(Recommended)` option.
3. **Implementation Plan Generation (`IMPLEMENTATION_PLAN.md`):**
   * After the user approves the alignment, generate **one single self-contained document** in the root: `IMPLEMENTATION_PLAN.md`.
   * **Do NOT** create the multi-folder `openspec/` hierarchy. Instead, encapsulate all implementation steps, exact code blueprints, test definitions, execution commands, and theoretical answers into this single markdown document.
   * Ensure the plan is so detailed, sequential, and explicit that an independent lightweight executor agent can carry it out start-to-finish without ambiguity, guessing, or errors.
4. **Final Execution Prompt Embedded in the Plan:**
   * At the very end of `IMPLEMENTATION_PLAN.md`, include an **Executor Prompt** enclosed in a fenced code block.
   * This prompt will allow the user to open a fresh terminal with `agy`, point to the plan, and instruct the lightweight agent to execute all tasks to completion.

---

## 4. Ready-to-Use Agent Activation Prompt

Copy and paste the prompt below into your target agent session (e.g., via `agy`):

```markdown
You are a Senior Distributed Systems & Blockchain Engineer working on Antigravity.
You must read and follow the handoff instructions in `HANDOFF_PLANNING.md` located at:
`atividade_pratica8/HANDOFF_PLANNING.md`

### Your Mission:
1. Ingest the handoff context: AP8 practical assignment, Document/Certificate Registry theme, and the core constraint of "minimum necessary effort with high quality, speed, and zero over-engineering".
2. Initiate an interactive `/grill-me` session with the user using the `ask_question` tool to resolve remaining tactical decisions (toolchain selection — Hardhat vs alternatives —, project file layout, and deliverable format). Present recommendations clearly.
3. Once aligned, draft a comprehensive, self-contained `IMPLEMENTATION_PLAN.md` in the project root (`atividade_pratica8`).
   - The plan must contain exact file paths, contract implementation specifications, automated test specifications, local deployment instructions, and pre-written answers for the report/questions.
   - At the bottom of `IMPLEMENTATION_PLAN.md`, write a clear, autonomous prompt for a lightweight executor agent so the user can run the implementation in a new terminal with zero friction.
```
