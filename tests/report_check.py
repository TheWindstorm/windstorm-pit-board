"""P67 (G20.6): a run that ends early is not a green run.

pytest exits 0 when a test ends its process with os._exit(0): no summary, no report, and the CI step is green
after one test of hundreds. CI therefore writes pytest's JUnit report and runs this after it:

    python -I tests/report_check.py report.xml tests/

It fails (exit 1, one line saying why) unless the report is there, can be read, and holds one case for every
test pytest collects in the given folder. Collected by pytest itself (`--collect-only -q`), never read from the
test run's own printed lines, which a test can print too.
"""
import subprocess
import sys
import xml.etree.ElementTree as ET


def collected(folder):
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", folder],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        return None
    return sum(1 for ln in r.stdout.splitlines() if "::" in ln)


def cases(report):
    try:
        root = ET.parse(report).getroot()
    except (OSError, ET.ParseError):
        return None
    return sum(1 for _ in root.iter("testcase"))


def main(argv):
    if len(argv) != 2:
        print("usage: report_check.py <junit report> <tests folder>")
        return 2
    report, folder = argv
    ran, want = cases(report), collected(folder)
    if ran is None:
        print(f"report_check: no readable test report at {report}: the run ended before pytest wrote it")
        return 1
    if want is None:
        print(f"report_check: pytest could not collect {folder}, so the report cannot be checked")
        return 1
    if ran != want:
        print(f"report_check: the report holds {ran} test(s) of the {want} collected: the run did not run them all")
        return 1
    print(f"report_check: {ran} of {want} collected tests are in the report")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
