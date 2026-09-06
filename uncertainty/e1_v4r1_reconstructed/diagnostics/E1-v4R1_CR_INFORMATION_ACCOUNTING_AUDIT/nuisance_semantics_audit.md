# X_B / X_F nuisance semantics audit

| Channel | X_B | X_F | Evidence |
|---|---|---|---|
| zV | MUST CANCEL | MUST CANCEL | `visual_evidence()` uses camera-target reprojection and per-view target-pose absorption only; its nuisance Jacobian is zero. |
| zR | MUST CANCEL | MUST ENTER | `relative_evidence()` deletes `T_BC` and sets only `jn[:,6:12]=Ad_X(Ad_A-I)`. Relative hand-eye consistency cancels a common base/camera transform; the fixed flange-side transform remains. |
| zL | UNRESOLVED FROM CURRENT EVIDENCE | UNRESOLVED FROM CURRENT EVIDENCE | `localization_evidence()` emits no nuisance columns. The recovered absolute equation has no documented X_B/X_F semantics. |
| zG | UNRESOLVED FROM CURRENT EVIDENCE | MUST ENTER under implemented equation | `geometry_residual()` inserts both left X_B and right X_F, but `geometry_evidence()` explicitly zeros X_B to preserve q1 information, while retaining X_F. The code labels zG Jacobian a reconstruction choice. |

`X_B=0` is physically implied for zV/zR by their implemented relative/camera-target equations. It is **C: impossible to decide from current recovered evidence** as a global E1 nuisance semantic, because zL has no recovered transform chain and zG explicitly suppresses a transform that its own residual initially contains. Thus the rank-0 X_B cannot be certified as a historical physical implication, nor proved an omission, from the available evidence. X_F is the sole implemented rank-6 nuisance: it enters zR and zG, with zG dominating its whitened rank.
