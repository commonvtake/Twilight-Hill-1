"""Build the inspected legacy SH map exporter for Linux, then export placed cafe geometry."""
from pathlib import Path
import subprocess,shutil
root=Path(__file__).resolve().parents[2];repo=root/'sh_ipd2obj';work=root/'tp_work';out=work/'cafe';out.mkdir(parents=True,exist_ok=True)
s=subprocess.check_output(['git','show','HEAD:main.c'],cwd=repo).decode().replace('\r\n','\n')
a=s.index('\t\t\tstrncpy(ipd_name,');b=s.index('sprintf(log_name,',a)
s=s[:a]+'''const char *base = strrchr(argv[i], '/');
base = base ? base + 1 : argv[i];
snprintf(ipd_name, sizeof(ipd_name), "%s", base);
char *dot = strrchr(ipd_name, '.'); if (dot) *dot = 0;
'''+s[b:]
s=s.replace('system("PAUSE");','/* Automated conversion. */').replace('static float scale = 0.003906;','static float scale = 0.00390625;').replace('static short map_max = 10246;','static short map_max = 10240;')
a=s.index('\tfor (i = 0; i < tplm.obj_num; i++)');b=s.index('\n\tlprintf("v_index',a);s=s[:a]+'/* Omit uninstantiated cutscene variants. */\n'+s[b:];(repo/'main.c').write_text(s)
s=subprocess.check_output(['git','show','HEAD:tim.c'],cwd=repo).decode().replace('\r\n','\n').replace('\tfclose(tg);\n\n\ttg = fopen(tga_name, "wb");','\tif (tg != NULL) fclose(tg);\n\n\ttg = fopen(tga_name, "wb");');(repo/'tim.c').write_text(s)
with (work/'exporter-compile.log').open('w') as log:subprocess.run(['gcc','-O2',str(repo/'main.c'),str(repo/'tim.c'),'-o',str(work/'ipd2obj')],stderr=log,check=True)
bg=root/'sh_work/assets/BG'
for p in list(bg.glob('*.TIM'))+[bg/'THR_GLB.PLM',bg/'THR0006.IPD']:shutil.copy2(p,out/p.name)
with (out/'conversion.log').open('w') as log:subprocess.run([str(work/'ipd2obj'),'THR0006.IPD'],cwd=out,stdout=log,stderr=log,check=True)
print(out/'THR0006.OBJ')
