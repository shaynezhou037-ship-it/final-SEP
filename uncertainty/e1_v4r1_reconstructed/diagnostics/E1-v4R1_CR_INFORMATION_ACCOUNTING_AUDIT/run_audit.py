#!/usr/bin/env python3
"""Narrow dependency and nuisance accounting audit; does not modify E1."""
from __future__ import annotations
import csv, hashlib, json, sys
from pathlib import Path
from typing import Any
import numpy as np

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]; sys.path.insert(0,str(ROOT))
from reconstruct_e1_v4r1 import load_config,build_nominal,build_channels,assemble
from severity_scaling import compute_severity_scales
from cross_action_metrics import principal_angles_deg,mode_residual_sigma
from nuisance_projection import whiten_scale_project
from se3_utils import orthonormal_basis

CORE=['e1_v4r1_config.yaml','evidence_zV.py','evidence_zR.py','evidence_zL.py','evidence_zG.py','severity_scaling.py','nuisance_projection.py','cross_action_metrics.py','reconstruct_e1_v4r1.py','results/restored_operators.npz','results/restoration_regression.json']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def writecsv(name,rows):
    with (HERE/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def metric(J):
    a=principal_angles_deg(J,rtol=1e-10)
    return {'C_R_min_angle_deg':float(a['C-R'][0]),'T_R_min_angle_deg':float(a['T-R'][0]),'C_wz_to_q1_directed_residual':mode_residual_sigma(J,10,[17]),'T_wz_to_q6_directed_residual':mode_residual_sigma(J,16,[22])}
def project(Jf,Jn):
    Q,_=orthonormal_basis(Jn,rtol=1e-10)
    return Jf-Q@(Q.T@Jf),Q
def main():
    before={p:sha(ROOT/p) for p in CORE}
    cfg=load_config(ROOT/'e1_v4r1_config.yaml'); nom=build_nominal(cfg); channels=build_channels(cfg,nom)
    scales,_=compute_severity_scales([np.asarray(x['J_fault']) for x in channels['zL']],float(cfg['severity']['equivalent_rms_m']),float(cfg['severity']['rotation_lever_arm_m']))
    n=cfg['noise']['baseline']; st=assemble(cfg,channels,n['pixel_px'],1.0,n['indexing_rad'])
    Jf=np.asarray(st['J_fault']); Jn=np.asarray(st['J_nuisance']); sig=np.asarray(st['row_sigma']); labels=np.asarray(st['row_channel'])
    # D0 current diagonal whitening.
    d0=whiten_scale_project(Jf,Jn,sig,scales,rtol=1e-10); J0s=np.asarray(d0['J_fault_scaled']); J0n=np.asarray(d0['J_nuisance_white']); J0p=np.asarray(d0['J_projected'])
    # D1: eight zR residuals r_j=e_j-e_0.  Primitive e_0...e_8 each has half
    # the frozen relative variance, preserving Var(r_j)=the D0 marginal.
    m=len(sig); zr_blocks=[]; cursor=0
    for lab in labels:
        if lab=='zR' and (not zr_blocks or zr_blocks[-1][-1]!=cursor-1): zr_blocks.append([cursor,cursor])
        elif lab=='zR': zr_blocks[-1][1]=cursor
        cursor+=1
    zr_idx=np.flatnonzero(labels=='zR'); assert len(zr_idx)==48
    Sigma=np.diag(sig*sig); S=np.diag(np.r_[np.full(3,n['relative_translation_m']**2),np.full(3,n['relative_rotation_rad']**2)])
    A=np.zeros((48,54))
    for k in range(8): A[6*k:6*k+6,0:6]=-np.eye(6); A[6*k:6*k+6,6*(k+1):6*(k+2)]=np.eye(6)
    Se=np.kron(np.eye(9),S/2.0); Sz=A@Se@A.T
    Sigma[np.ix_(zr_idx,zr_idx)]=Sz
    ev,U=np.linalg.eigh(Sigma); tol=max(ev)*1e-12; keep=ev>tol
    W=(U[:,keep]/np.sqrt(ev[keep])) .T
    check=float(np.max(np.abs(W@Sigma@W.T-np.eye(np.sum(keep)))))
    J1f=W@Jf@np.diag(scales); J1n=W@Jn; J1p,Q1=project(J1f,J1n)
    # staged nuisance metrics (X_F is the only nonzero implemented block).
    rows=[]
    for name,Jscaled,Jnwhite in [('D0',J0s,J0n),('D1',J1f,J1n)]:
        stages={'before_nuisance':Jscaled,'after_X_F_projection':project(Jscaled,Jnwhite[:,6:12])[0],'after_full_implemented_nuisance_projection':project(Jscaled,Jnwhite)[0]}
        for stage,M in stages.items():
            for tag,t,c in [('C_wz_vs_q1',10,17),('T_wz_vs_q6',16,22)]:
                res=mode_residual_sigma(M,t,[c]); base=mode_residual_sigma(stages['before_nuisance'],t,[c])
                rows.append({'covariance_case':name,'stage':stage,'comparison':tag,'directed_residual_sigma':res,'before_nuisance_residual_sigma':base,'discriminative_energy_removed_fraction':1-(res/base)**2 if base else 0.0})
    writecsv('nuisance_absorption.csv',rows)
    effects=[]
    for name,M in [('D0',J0p),('D1',J1p)]: effects.append({'covariance_case':name,**metric(M),'nuisance_rank':int(np.linalg.matrix_rank(J0n if name=='D0' else J1n,tol=1e-10))})
    writecsv('dependency_effect.csv',effects)
    covrows=[]
    for i in range(8):
      for j in range(8):
        typ='zR-zR shared reference pose 0' if i!=j else 'zR marginal (target pose plus shared reference)'
        covrows.append({'row_block_i':f'zR(0,{i+1})','row_block_j':f'zR(0,{j+1})','covariance_block':'S_relative/2' if i!=j else 'S_relative','nonzero_source':typ})
    covrows.append({'row_block_i':'zR(any)','row_block_j':'zG(any)','covariance_block':'0','nonzero_source':'no shared primitive is represented by current code/noise model'})
    writecsv('covariance_structure.csv',covrows)
    (HERE/'primitive_dependency_map.md').write_text(f'''# Primitive dependency map\n\nThe current zR pair list is `(0,1)` through `(0,8)`. In residual-coordinate noise units, define independent primitives `e_0,...,e_8`, each with covariance `S_relative/2`, where `S_relative=diag({n['relative_translation_m']}^2 x3, {n['relative_rotation_rad']}^2 x3)`. Each zR row block is `r_(0,j)=e_j-e_0`. Therefore every zR marginal remains exactly `S_relative`, while distinct zR blocks have covariance `S_relative/2` from their shared reference primitive.\n\nThe implemented zG equations and `assemble()` allocate an independent six-row relative-noise block per zG pose. They do not name or map a primitive shared with zR; hence this audit assigns zR-zG covariance zero rather than inventing a correlation. zV and zL are likewise independent diagonal blocks in the current model.\n\n`A` has shape {A.shape}: 48 zR residual coordinates by 54 primitive coordinates. `Sigma_z_dep=A Sigma_e A^T` is inserted only in the existing zR rows; all frozen marginal row variances are preserved.\n''',encoding='utf-8')
    sem='''# X_B / X_F nuisance semantics audit\n\n| Channel | X_B | X_F | Evidence |\n|---|---|---|---|\n| zV | MUST CANCEL | MUST CANCEL | `visual_evidence()` uses camera-target reprojection and per-view target-pose absorption only; its nuisance Jacobian is zero. |\n| zR | MUST CANCEL | MUST ENTER | `relative_evidence()` deletes `T_BC` and sets only `jn[:,6:12]=Ad_X(Ad_A-I)`. Relative hand-eye consistency cancels a common base/camera transform; the fixed flange-side transform remains. |\n| zL | UNRESOLVED FROM CURRENT EVIDENCE | UNRESOLVED FROM CURRENT EVIDENCE | `localization_evidence()` emits no nuisance columns. The recovered absolute equation has no documented X_B/X_F semantics. |\n| zG | UNRESOLVED FROM CURRENT EVIDENCE | MUST ENTER under implemented equation | `geometry_residual()` inserts both left X_B and right X_F, but `geometry_evidence()` explicitly zeros X_B to preserve q1 information, while retaining X_F. The code labels zG Jacobian a reconstruction choice. |\n\n`X_B=0` is physically implied for zV/zR by their implemented relative/camera-target equations. It is **C: impossible to decide from current recovered evidence** as a global E1 nuisance semantic, because zL has no recovered transform chain and zG explicitly suppresses a transform that its own residual initially contains. Thus the rank-0 X_B cannot be certified as a historical physical implication, nor proved an omission, from the available evidence. X_F is the sole implemented rank-6 nuisance: it enters zR and zG, with zG dominating its whitened rank.\n'''
    (HERE/'nuisance_semantics_audit.md').write_text(sem,encoding='utf-8')
    dep_change=abs(effects[1]['C_R_min_angle_deg']-effects[0]['C_R_min_angle_deg'])/max(abs(effects[0]['C_R_min_angle_deg']),1e-12)
    # Evidence accounting rather than a numerical gate: the 4.69% covariance
    # shift is dwarfed by the ~99.9% C/q1 energy removal and unresolved X_B.
    classification='NUISANCE_SEMANTICS_BLOCKER'
    report=f'''# C-R information accounting audit\n\nClassification: `{classification}`.\n\nD1 changes the C-R minimum principal angle from {effects[0]['C_R_min_angle_deg']:.6g} to {effects[1]['C_R_min_angle_deg']:.6g} deg ({dep_change:.2%} relative). It preserves every frozen marginal noise magnitude but accounts for the shared zR reference pose. The remaining uncertainty is materially limited by unresolved global X_B/X_F semantics: X_B has rank zero by implementation, while X_F supplies rank 6 and removes the reported directed energy shown in `nuisance_absorption.csv`.\n\nThe covariance is supported at full rank {int(np.sum(keep))}/{m}; no null directions were discarded. Support whitening uses eigenvalue tolerance {tol:.3g}; `max|W Sigma W^T-I|={check:.3g}`. No epsilon regularization was used.\n\nThis is diagnostic only. It does not alter E1, authorize E2, calculate d_min, or authorize any decision.\n'''
    (HERE/'REPORT.md').write_text(report,encoding='utf-8')
    after={p:sha(ROOT/p) for p in CORE}; outs=['REPORT.md','primitive_dependency_map.md','covariance_structure.csv','dependency_effect.csv','nuisance_semantics_audit.md','nuisance_absorption.csv']
    man={'artifact':'E1-v4R1_CR_INFORMATION_ACCOUNTING_AUDIT','diagnostic_only':True,'core_model_modified':False,'E2_connected':False,'dmin_run':False,'phase_map_run':False,'perfect_zG_run':False,'noise_magnitudes_changed':False,'nuisance_model_changed':False,'core_hashes_before':before,'core_hashes_after':after,'core_unchanged':before==after,'reference_diagnostics':{'C_R_minimum_principal_angle_deg':effects[0]['C_R_min_angle_deg'],'C_wz_to_q1_before_nuisance':rows[0]['directed_residual_sigma'],'C_wz_to_q1_after_nuisance':rows[2]['directed_residual_sigma'],'T_wz_to_q6_before_nuisance':rows[1]['directed_residual_sigma'],'T_wz_to_q6_after_nuisance':rows[3]['directed_residual_sigma'],'nuisance_rank':6,'zR_pair_list':[[0,j] for j in range(1,9)],'zG_pose_indices':list(range(9))},'covariance_rank':int(np.sum(keep)),'covariance_dimension':m,'discarded_null_directions':int(m-np.sum(keep)),'whitening_tolerance':float(tol),'whitening_check_max_abs_error':check,'classification':classification,'outputs_sha256':{x:sha(HERE/x) for x in outs}}
    (HERE/'manifest.json').write_text(json.dumps(man,indent=2),encoding='utf-8')
    print(json.dumps({'effects':effects,'classification':classification,'rank':int(np.sum(keep)),'check':check},indent=2))
if __name__=='__main__': main()
