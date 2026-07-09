"""semver比較の隠しテスト。version_compare(a,b) -> -1/0/1 を検証。
subtle correctnessの罠(prerelease優先順位)を重点的に突く。"""
import sys, importlib.util

def load(path):
    spec = importlib.util.spec_from_file_location("sv", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def find_fn(m):
    for name in ("version_compare","compare","cmp_version","compare_versions"):
        if hasattr(m, name): return getattr(m, name)
    for name in dir(m):
        o = getattr(m, name)
        if callable(o) and not name.startswith("_"):
            try:
                if o("1.0.0","1.0.0")==0: return o
            except Exception: pass
    raise RuntimeError("比較関数が見つからない")

def run(path):
    f = find_fn(load(path))
    def sign(x): return (x>0)-(x<0)
    cases = [
        # (a, b, expected sign, カテゴリ)
        ("1.0.0","1.0.1",-1,"基本:patch"),
        ("1.2.0","1.1.9", 1,"基本:minor"),
        ("2.0.0","1.9.9", 1,"基本:major"),
        ("1.0.0","1.0.0", 0,"基本:等価"),
        # --- subtle: prerelease ---
        ("1.0.0-alpha","1.0.0",-1,"罠:prerelease<release"),
        ("1.0.0","1.0.0-alpha", 1,"罠:release>prerelease"),
        ("1.0.0-alpha","1.0.0-alpha.1",-1,"罠:少ないフィールド<多い"),
        ("1.0.0-alpha.1","1.0.0-alpha.2",-1,"罠:数値識別子の大小"),
        ("1.0.0-alpha","1.0.0-beta",-1,"罠:英字識別子の辞書順"),
        ("1.0.0-alpha.1","1.0.0-alpha.beta",-1,"罠:数値<英字"),
        ("1.0.0-rc.1","1.0.0-rc.1", 0,"罠:prerelease等価"),
    ]
    out=[]
    for a,b,exp,cat in cases:
        try: got=sign(f(a,b))
        except Exception as e: out.append((cat,f"{a} vs {b}",False,f"EXC:{type(e).__name__}")); continue
        out.append((cat,f"{a} vs {b}",got==exp,f"got={got} exp={exp}"))
    return out

if __name__=="__main__":
    try: rs=run(sys.argv[1])
    except Exception as e: print(f"ROBUST_FAIL: {type(e).__name__}: {e}"); sys.exit(2)
    basic=sum(1 for c,_,ok,_ in rs if ok and c.startswith("基本"))
    trap =sum(1 for c,_,ok,_ in rs if ok and c.startswith("罠"))
    for cat,desc,ok,info in rs:
        print(f"  [{'PASS' if ok else 'FAIL'}] {cat}: {desc}  ({info})")
    nb=sum(1 for c,_,_,_ in rs if c.startswith('基本')); nt=sum(1 for c,_,_,_ in rs if c.startswith('罠'))
    print(f"基本: {basic}/{nb}  |  罠(subtle): {trap}/{nt}")
    sys.exit(0 if basic+trap==len(rs) else 1)
