from pathlib import Path
import shutil
w=Path(__file__).resolve().parents[1]
old=w/'atomOS_3_6_1_7_COUPLED'; new=w/'atomOS_3_6_1_8_LIVE'
assert not new.exists()
def ignore(folder,names):
    return [n for n in names if (Path(folder)/n).is_dir() and (n in {'results','results_3_6_1_5','results_3_6_1_6','bin','output','.build','__pycache__','.git','tmp'} or n.startswith('build')) or n=='SHA256SUMS.txt']
shutil.copytree(old,new,ignore=ignore)
(new/'results').mkdir()
shutil.copy2(old/'results/validation_status.json',new/'source/baseline_3_6_1_7_validation.json')
shutil.copy2(old/'output/pdf/aTOMos_v3_6_1_7_Coupled_Geometry_Physical_Kernel_UGTS_Tom_Klootwijk.pdf',new/'source/parent_3_6_1_7.pdf')
print(new)
