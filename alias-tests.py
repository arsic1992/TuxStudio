import subprocess,sys,json
base='func calculate(x as int, y as int = 2) as int with alias("calc", "shortName") { return x * y }\n'
cases=[(base+'display(calculate(3), calc(3), shortName(3, y: 4))','6 6 12'),('display(calc(3))\n'+base,'6'),(base+'3 |> calc() |> display()','6'),('func f(n as int) as int with alias("again") { if n == 0 { return 0 }; return 1 + again(n - 1) }\ndisplay(f(4))','4'),('func f(x) with alias("g") => x + 1\ndisplay(g(2))','3'),(base+'var f = calc\ndisplay(f(5))','10'),(base+'calc = 1',None),(base+'var calc = 1',None),(base+'calc("bad")',None),('func f() with alias("f") {}',None),('func f() with alias("display") {}',None),('func f() with alias("a", "a") {}',None),('func f() with alias("a-b") {}',None),('func f() with alias("a") {}\nfunc g() with alias("a") {}',None),('func f() with alias("a") {}\nfunc a() {}',None),('func f() with alias("a{1}") {}',None),('class C { func f() with alias("g") {} }',None)]
for src,expected in cases:
 p=subprocess.run([sys.executable,'TuxStudio.py','--tux-worker'],input=json.dumps([src,'Restricted'])+'\n',text=True,capture_output=True,timeout=5)
 out=''.join(v for k,v in map(json.loads,p.stdout.splitlines()) if k=='output'); ok='[Execution finished]' in out
 assert (ok and out.splitlines()[0]==expected) if expected is not None else not ok,(src,out,p.stderr)
 print('PASS',src.splitlines()[-1],repr(out[:150]))
