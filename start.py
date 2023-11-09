import os
import subprocess

if not os.environ.get("VIRTUAL_ENV"):
    print("Not running in a virtual environment. Launching 'poetry shell'...")
    with open("start_error_log.txt", "w") as error_file:
        subprocess.run(
            "poetry run python start.py",
            shell=True,
            stderr=error_file,
        )
else:
    from dotenv import load_dotenv

    load_dotenv()
    command = "interpreter"
    subprocess.run(command, shell=True)
