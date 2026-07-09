"""独自仕様(公開標準にない)区間マージの隠しテスト。
正解の定義: merge_intervals(intervals, tolerance) は
  - 各区間 [start,end] (start<=end) のリスト。入力はソートされているとは限らない。
  - 2区間は「重なる or 間隙gap<=tolerance」なら統合する。gap = 次のstart - 現在のend。
  - 接触 [0,10],[10,20] は gap=0 なので常に統合。
  - gap==tolerance はギリギリ統合(<=)。gap==tolerance+1 は非統合。
  - 出力はstart昇順、統合済みで、隣接区間間のgapは常に tolerance より大きい。
この「gap<=tolerance」「接触=統合」「境界は<=」がsubtle correctnessの罠。
"""
import sys, importlib.util

def load(path):
    spec = importlib.util.spec_from_file_location("iv", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def find_fn(m):
    for name in ("merge_intervals","merge","merge_ranges"):
        if hasattr(m,name): return getattr(m,name)
    for name in dir(m):
        o=getattr(m,name)
        if callable(o) and not name.startswith("_"):
            try:
                if o([[0,10],[10,20]],0)==[[0,20]]: return o
            except Exception: pass
    raise RuntimeError("merge関数が見つからない")

def norm(x):
    return [list(p) for p in x]

def run(path):
    f=find_fn(load(path))
    cases=[
        # (intervals, tolerance, expected, カテゴリ)
        ([[1,3],[6,9]], 0, [[1,3],[6,9]], "基本:非統合"),
        ([[1,5],[3,8]], 0, [[1,8]], "基本:重なり統合"),
        ([[0,10],[10,20]], 0, [[0,20]], "罠:接触は統合"),
        ([[0,10],[12,20]], 2, [[0,20]], "罠:gap==tol は統合(<=)"),
        ([[0,10],[13,20]], 2, [[0,10],[13,20]], "罠:gap==tol+1 は非統合"),
        ([[10,20],[0,5]], 0, [[0,5],[10,20]], "罠:未ソート入力"),
        ([[0,20],[5,8]], 0, [[0,20]], "罠:入れ子(内包)"),
        ([], 0, [], "罠:空入力"),
        ([[3,7]], 5, [[3,7]], "罠:単一区間"),
    ]
    out=[]
    for iv,tol,exp,cat in cases:
        try:
            got=norm(f([list(p) for p in iv], tol))
            out.append((cat,f"{iv} tol={tol}", got==exp, f"got={got} exp={exp}"))
        except Exception as e:
            out.append((cat,f"{iv} tol={tol}", False, f"EXC:{type(e).__name__}:{e}"))
    return out

if __name__=="__main__":
    try: rs=run(sys.argv[1])
    except Exception as e: print(f"ROBUST_FAIL: {type(e).__name__}: {e}"); sys.exit(2)
    b=sum(1 for c,_,ok,_ in rs if ok and c.startswith("基本"))
    t=sum(1 for c,_,ok,_ in rs if ok and c.startswith("罠"))
    for cat,desc,ok,info in rs:
        print(f"  [{'PASS' if ok else 'FAIL'}] {cat}: {desc}")
        if not ok: print(f"         {info}")
    nb=sum(1 for c,_,_,_ in rs if c.startswith('基本')); nt=sum(1 for c,_,_,_ in rs if c.startswith('罠'))
    print(f"基本: {b}/{nb}  |  罠(subtle): {t}/{nt}")
    sys.exit(0 if b+t==len(rs) else 1)
