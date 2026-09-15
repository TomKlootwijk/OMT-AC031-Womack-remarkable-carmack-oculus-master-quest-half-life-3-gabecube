"""Persistent native SATNAV-STREAM-1 client; every response comes from C++/CUDA."""
from __future__ import annotations
import hashlib,json,queue,subprocess,threading
from pathlib import Path

class NativeSolver:
    def __init__(self,binary,backend='cpu',device=0,timeout=15.0):
        self.binary=Path(binary).resolve(strict=True)
        self.binary_sha256=hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.timeout=timeout
        self.command=[str(self.binary),'--backend',backend,'--device',str(device)]
        self.process=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
        self.responses=queue.Queue();self.errors=[];self.closed=False
        def reader():
            for line in self.process.stdout:self.responses.put(line)
            self.responses.put(None)
        def errors():
            for line in self.process.stderr:self.errors.append(line.rstrip())
        self.reader=threading.Thread(target=reader,daemon=True);self.reader.start()
        self.error_reader=threading.Thread(target=errors,daemon=True);self.error_reader.start()
        try:
            self.ready=self._receive()
            if self.ready.get('type')!='ready' or self.ready.get('protocol')!='SATNAV-STREAM-1':raise RuntimeError('unexpected native worker greeting')
        except BaseException:
            self.close();raise
    def _receive(self):
        try:line=self.responses.get(timeout=self.timeout)
        except queue.Empty:raise TimeoutError('native solver response deadline exceeded')
        if line is None:raise RuntimeError('native worker ended: '+'; '.join(self.errors))
        response=json.loads(line)
        if response.get('type')=='error':raise ValueError('native request rejected: '+response['message'])
        return response
    def request(self,line):
        if self.closed:raise RuntimeError('native worker closed')
        if '\n' in line or '\r' in line:raise ValueError('one request per line')
        self.process.stdin.write(line+'\n');self.process.stdin.flush()
        try:return self._receive()
        except (TimeoutError,RuntimeError,json.JSONDecodeError):
            # A late response could otherwise be mistaken for the next request.
            self.close();raise
    def solve(self,epoch_id,time_gpst_s,seed,observations,asa=0xffffffff,na=0xffffffff,boundary=0):
        if len(seed)!=4:raise ValueError('four seed components required')
        fields=['SOLVE',str(epoch_id),format(time_gpst_s,'.17g'),*[format(float(v),'.17g') for v in seed],str(asa),str(na),str(boundary),str(len(observations))]
        for o in observations:
            fields.append(str(o['channel']))
            fields.extend(format(float(o[k]),'.17g') for k in ('sx_rx_m','sy_rx_m','sz_rx_m','code_m','add_correction_m','sigma_m'))
            fields.append(str(int(o.get('ready',1))))
        result=self.request(' '.join(fields))
        if result.get('type')!='solution' or result.get('epoch_id')!=epoch_id:raise RuntimeError('native response identity mismatch')
        return result
    def close(self):
        if getattr(self,'closed',True):return
        self.closed=True
        if self.process.poll() is None:
            try:self.process.stdin.write('QUIT\n');self.process.stdin.flush();self.process.wait(timeout=2)
            except (OSError,subprocess.TimeoutExpired):self.process.kill();self.process.wait(timeout=2)
        self.reader.join(timeout=1);self.error_reader.join(timeout=1)
        for handle in (self.process.stdin,self.process.stdout,self.process.stderr):
            if handle:handle.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
