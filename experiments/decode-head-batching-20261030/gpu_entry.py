"""Head fixture entry inside the existing canonical window; no standalone launch authority."""
import argparse
from pathlib import Path
import gpu_check as g


def main(argv=None):
    if Path(g.__file__).resolve()!=Path(__file__).resolve().with_name('gpu_check.py'):
        raise ValueError('Foreign kernel controller import')
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--proof',type=Path,required=True)
    args=parser.parse_args(argv)
    return g.fixture_phase(args.output,args.proof)


if __name__=='__main__':raise SystemExit(main())
