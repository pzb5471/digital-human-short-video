import argparse, json, math, shutil
from pathlib import Path, PureWindowsPath

class PreparationError(ValueError): pass
def _owned(root,value):
 if Path(value).is_absolute() or PureWindowsPath(value).is_absolute(): raise PreparationError("asset path must be project-relative")
 p=(root/value).resolve()
 try:p.relative_to(root)
 except ValueError as e: raise PreparationError("asset path escapes project root") from e
 if not p.is_file(): raise PreparationError(f"asset missing: {value}")
 return p
def prepare_remotion(project_file,out_dir):
 project_file=Path(project_file).resolve(); root=project_file.parent; out=Path(out_dir).resolve()
 if tuple(part.lower() for part in out.parts[-2:]) != ("public","project"): raise PreparationError("output must be template/public/project")
 out.mkdir(parents=True,exist_ok=True); doc=json.loads(project_file.read_text(encoding="utf-8"))
 if not doc.get("provider_original"): raise PreparationError("provider_original is required")
 used=set()
 def copy(key):
  if not doc.get(key): return None
  source=_owned(root,doc[key]); target=out/source.name
  if target.name in used: raise PreparationError("asset filename collision")
  used.add(target.name); shutil.copy2(source,target); return f"project/{target.name}"
 props={"primaryVideo":copy("provider_original"),"logo":copy("logo"),"brandBackground":copy("brand_background"),"bgm":copy("bgm"),"hook":doc.get("hook",""),"cta":doc.get("cta",""),"broll":[],"captions":doc.get("captions",[])}
 for cue in props["captions"]:
  lines=cue.get("lines",[])[:2]; line_index=0; cursor=0
  for word in cue.get("words",[]):
   if word.get("line") in (0,1): continue
   text=str(word.get("text","")); found=lines[line_index].find(text,cursor) if line_index<len(lines) else -1
   if found<0 and line_index+1<len(lines): line_index+=1; cursor=0; found=lines[line_index].find(text,cursor)
   word["line"]=min(line_index,1); cursor=(found+len(text)) if found>=0 else cursor
 for item in doc.get("broll",[]):
  source=_owned(root,item["path"]); target=out/source.name
  if target.name in used: raise PreparationError("asset filename collision")
  used.add(target.name); shutil.copy2(source,target); start=math.ceil(item["start_ms"]*30/1000); end=math.ceil(item["end_ms"]*30/1000); props["broll"].append({"src":f"project/{target.name}","from":start,"durationInFrames":end-start})
 props["durationInFrames"]=math.ceil(max([doc.get("duration_ms",3000)]+[item.get("end_ms",0) for item in doc.get("broll",[])]+[cue.get("end_ms",0) for cue in props["captions"]])*30/1000)
 (out.parent.parent/"src"/"fixture-props.json").parent.mkdir(parents=True,exist_ok=True); (out.parent.parent/"src"/"fixture-props.json").write_text(json.dumps(props,ensure_ascii=False),encoding="utf-8")
 return props
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("project");p.add_argument("out");a=p.parse_args();prepare_remotion(a.project,a.out)
