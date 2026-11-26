import subprocess, sys, json
p = subprocess.run([sys.argv[1], '--tux-worker'], input=json.dumps(['display(6 * 7)', 'Restricted'])+'\n', text=True, capture_output=True, timeout=20, check=True)
messages = [json.loads(line) for line in p.stdout.splitlines()]
output = ''.join(v for k,v in messages if k == 'output')
assert '42\n' in output and '[Execution finished]' in output, output
print('Worker smoke test passed')
