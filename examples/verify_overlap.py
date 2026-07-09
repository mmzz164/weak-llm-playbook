"""反直感ルールの隠しテスト。
正解の定義: merge_overlaps(intervals) は
  - 2区間は「厳密に重なる(点より広く交差)」ときだけ統合する。
  - 接触 [10,20],[20,30] は端点20を共有するだけなので【統合しない】(標準の区間マージと逆)。
  - 入れ子 [0,20],[5,8] は統合する。[0,10],[5,15] は統合 → [0,15]。
  - 出力は start 昇順。
この「接触は統合しない(点の共有は重なりに非ず)」が反直感の罠。標準マージは接触を統合するので、
弱LLMが訓練データの標準挙動に引きずられると必ずここを外す。
"""
import sys, importlib.util
def load(path):
    spec=importlib.util.spec_from_file_location("ov",path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def find_fn(m):
    for name in ("merge_overlaps","merge_intervals","merge"):
        if hasattr(m,name): return getattr(m,name)
    for name in dir(m):
        o=getattr(m,name)
        if callable(o) and not name.startswith("_"):
            try:
                if o([[0,10],[5,15]])==[[0,15]]: return o
            except Exception: pass
    raise RuntimeError("関数が見つからない")
def norm(x): return [list(p) for p in x]
def run(path):
    f=find_fn(load(path))
    cases=[
        ([[1,3],[5,8]], [[1,3],[5,8]], "基本:離れて非統合"),
        ([[0,10],[5,15]], [[0,15]], "基本:重なり統合"),
        ([[10,20],[20,30]], [[10,20],[20,30]], "罠:接触は非統合(反直感)"),
        ([[0,20],[5,8]], [[0,20]], "罠:入れ子は統合"),
        ([[20,30],[10,20]], [[10,20],[20,30]], "罠:未ソート+接触非統合"),
        ([[0,5],[5,10],[10,15]], [[0,5],[5,10],[10,15]], "罠:連鎖接触は全て非統合"),
        ([[0,10],[2,4],[6,8]], [[0,10]], "罠:複数内包"),
    ]
    out=[]
    for iv,exp,cat in cases:
        try: got=norm(f([list(p) for p in iv]))
        except Exception as e: out.append((cat,str(iv),False,f"EXC:{type(e).__name__}")); continue
        out.append((cat,str(iv),got==exp,f"got={got} exp={exp}"))
    return out
if __name__=="__main__":
    try: rs=run(sys.argv[1])
    except Exception as e: print(f"ROBUST_FAIL: {e}"); sys.exit(2)
    b=sum(1 for c,_,ok,_ in rs if ok and c.startswith("基本"))
    t=sum(1 for c,_,ok,_ in rs if ok and c.startswith("罠"))
    for cat,desc,ok,info in rs:
        print(f"  [{'PASS' if ok else 'FAIL'}] {cat}: {desc}")
        if not ok: print(f"         {info}")
    nb=sum(1 for c,_,_,_ in rs if c.startswith('基本')); nt=sum(1 for c,_,_,_ in rs if c.startswith('罠'))
    print(f"基本: {b}/{nb}  |  罠(反直感): {t}/{nt}")
    sys.exit(0 if b+t==len(rs) else 1)
