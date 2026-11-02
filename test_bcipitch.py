# BEACON COMPUTING INITIATIVE | Developer Seal: CJB-DEV-2026
import tempfile
from pathlib import Path
from bcipitch import install, process, validate

def test_full_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        install(root)
        a=process(root,100)
        assert a['events']==100 and a['measures']==100 and a['octets']==13
        v=validate(root)
        assert v['octet_sizes']==[8]*12+[4]
        assert not v['errors']
        b=process(root,100)
        assert b['new_events']==0 and b['octets']==13

def test_partial():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        install(root);process(root,7)
        assert validate(root)['octet_sizes']==[7]
