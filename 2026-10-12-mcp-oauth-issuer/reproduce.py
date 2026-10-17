"""BEFORE: the conditional check is skipped exactly when discovery returns nothing."""

from pattern import report, run_scenarios

if __name__ == "__main__":
    print("BEFORE (check runs only if an expected issuer was discovered)")
    print(report(run_scenarios(fixed=False)))
