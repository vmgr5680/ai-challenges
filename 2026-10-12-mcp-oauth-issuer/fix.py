"""AFTER: the expected issuer is computed before any metadata is read, so the check always runs."""

from pattern import report, run_scenarios

if __name__ == "__main__":
    print("AFTER (expected issuer derived up front, fail closed)")
    print(report(run_scenarios(fixed=True)))
