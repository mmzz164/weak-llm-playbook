"""LRUキャッシュ成果物の独立検証。両条件の lru.py に対して同一の隠しテストを当てる。"""
import sys, importlib.util

def load(path):
    spec = importlib.util.spec_from_file_location("lru_mod", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def find_cache_cls(m):
    # LRUCache という名前を優先、なければ get/put を持つクラスを探す
    for name in dir(m):
        obj = getattr(m, name)
        if isinstance(obj, type) and hasattr(obj, "get") and hasattr(obj, "put"):
            return obj
    raise RuntimeError("get/put を持つクラスが見つからない")

def run(path):
    m = load(path)
    C = find_cache_cls(m)
    results = []
    def check(name, cond):
        results.append((name, bool(cond)))

    # 1. 基本 put/get
    c = C(2); c.put(1,1); c.put(2,2)
    check("基本get", c.get(1)==1)
    # 2. 容量超過でLRU退避
    c.put(3,3)  # key2 が退避されるはず
    check("LRU退避", c.get(2) in (-1, None))
    check("退避後の生存", c.get(3)==3)
    # 3. getでアクセスした要素は最近使用に昇格
    c = C(2); c.put(1,1); c.put(2,2); c.get(1); c.put(3,3)  # key2退避のはず
    check("getで昇格", c.get(1)==1 and c.get(2) in (-1,None))
    # 4. 既存キーの更新は退避を起こさない
    c = C(2); c.put(1,1); c.put(2,2); c.put(1,10)
    check("既存更新", c.get(1)==10 and c.get(2)==2)
    # 5. 容量1
    c = C(1); c.put(1,1); c.put(2,2)
    check("容量1", c.get(1) in (-1,None) and c.get(2)==2)
    # 6. 未登録キー
    c = C(2)
    check("未登録", c.get(99) in (-1,None))

    return results

if __name__ == "__main__":
    path = sys.argv[1]
    try:
        rs = run(path)
    except Exception as e:
        print(f"ROBUST_FAIL: {type(e).__name__}: {e}")
        sys.exit(2)
    passed = sum(1 for _,ok in rs if ok)
    for name, ok in rs:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"合計: {passed}/{len(rs)}")
    sys.exit(0 if passed==len(rs) else 1)
