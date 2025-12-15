import builtins
from datetime import datetime
from colorama import Fore, Style, init
import os


class TimestampedPrint:

    def __init__(self, log_file: str = "log.txt", color: bool = True):
        """Ersetzt print() durch eine Version mit Zeitstempel und Logfile."""
        self.log_file = log_file
        self.color = color
        self.original_print = builtins.print

        # Stelle sicher, dass colorama initialisiert ist (für Windows)
        init(autoreset=True)

        # Original print überschreiben
        builtins.print = self._custom_print

        # Stelle sicher, dass das Logfile existiert
        if not os.path.exists(log_file):
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("=== Log gestartet: " +
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S") +
                        " ===\n")

    def _custom_print(self, *args, **kwargs):
        """Interne Funktion, ersetzt print()."""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        text = " ".join(map(str, args))

        # Mit Farbe (optional)
        if self.color:
            prefix = f"{Fore.LIGHTGREEN_EX}{timestamp}{Style.RESET_ALL}"
        else:
            prefix = timestamp

        # In die Konsole ausgeben
        self.original_print(prefix, text, **kwargs)

        # In Logdatei schreiben
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} {text}\n")

    def restore(self):
        """Setzt print() wieder auf das Original zurück."""
        builtins.print = self.original_print
