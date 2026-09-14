import io
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RowError:
    row: int
    field: str
    message: str


@dataclass
class ValidationReport:
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    errors: list[RowError] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and self.total_rows > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "is_valid": self.is_valid,
            "errors": [e.__dict__ for e in self.errors],
        }

    def error_report_csv(self) -> str:
        buf = io.StringIO()
        buf.write("row,field,message\n")
        for e in self.errors:
            safe_message = e.message.replace('"', "'")
            buf.write(f'{e.row},{e.field},"{safe_message}"\n')
        return buf.getvalue()
