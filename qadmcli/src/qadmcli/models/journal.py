"""Journal-related data models."""

from typing import Any

from pydantic import BaseModel, Field


class JournalEntry(BaseModel):
    """Journal entry data."""

    entry_number: int = Field(..., description="Journal entry sequence number")
    entry_timestamp: str | None = Field(None, description="Entry timestamp")
    job_name: str | None = Field(None, description="Job that made the change")
    job_user: str | None = Field(None, description="User who ran the job")
    job_number: str | None = Field(None, description="Job number")
    program_name: str | None = Field(None, description="Program that made the change")
    
    # Journal entry type codes
    code: str | None = Field(None, description="Journal entry code (e.g., 'R' for record)")
    entry_type: str | None = Field(None, description="Entry type (PT=Insert, UP=Update, DL=Delete)")
    
    # Object information
    object_library: str | None = Field(None, description="Library of the object")
    object_name: str | None = Field(None, description="Name of the object")
    object_type: str | None = Field(None, description="Type of the object")
    
    # Record data
    before_image: dict[str, Any] | None = Field(None, description="Before image for updates/deletes")
    after_image: dict[str, Any] | None = Field(None, description="After image for inserts/updates")
    
    # Raw entry data
    raw_entry_data: str | None = Field(None, description="Raw journal entry data")

    @property
    def operation(self) -> str:
        """Get human-readable operation name."""
        mapping = {
            "PT": "INSERT",
            "UP": "UPDATE", 
            "DL": "DELETE",
            "BR": "BEFORE IMAGE",
            "UR": "AFTER IMAGE",
            "DR": "DIRECT",
        }
        return mapping.get(self.entry_type, self.entry_type)

    def to_sql(self) -> str | None:
        """Convert journal entry to SQL statement."""
        table = f"{self.object_library}.{self.object_name}" if self.object_library and self.object_name else "TABLE"
        
        if self.entry_type == "PT":  # Insert
            if self.after_image:
                cols = ", ".join(self.after_image.keys())
                vals = ", ".join(self._format_value(v) for v in self.after_image.values())
                return f"INSERT INTO {table} ({cols}) VALUES ({vals});"
        
        elif self.entry_type == "UP":  # Update
            if self.after_image:
                sets = ", ".join(f"{k} = {self._format_value(v)}" for k, v in self.after_image.items())
                where = ""
                if self.before_image:
                    where = " WHERE " + " AND ".join(
                        f"{k} = {self._format_value(v)}" 
                        for k, v in self.before_image.items()
                    )
                return f"UPDATE {table} SET {sets}{where};"
        
        elif self.entry_type == "DL":  # Delete
            where = ""
            if self.before_image:
                where = " WHERE " + " AND ".join(
                    f"{k} = {self._format_value(v)}" 
                    for k, v in self.before_image.items()
                )
            return f"DELETE FROM {table}{where};"
        
        return None

    def _format_value(self, value: Any) -> str:
        """Format a value for SQL."""
        if value is None:
            return "NULL"
        if isinstance(value, str):
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)


class JournalInfo(BaseModel):
    """Journal information for a table."""

    table_name: str
    table_library: str
    is_journaled: bool = False
    journal_library: str | None = None
    journal_name: str | None = None
    journal_receiver_library: str | None = None
    journal_receiver_name: str | None = None
    
    # Journal write mode (BEFORE/AFTER/BOTH)
    journal_images: str | None = None
    
    # Receiver timestamps
    receiver_attach_timestamp: str | None = None
    receiver_detach_timestamp: str | None = None
    
    # Entry range (table-specific)
    oldest_entry_sequence: int | None = None
    newest_entry_sequence: int | None = None
    oldest_entry_timestamp: str | None = None
    newest_entry_timestamp: str | None = None
    
    # Statistics
    total_entries: int | None = None
    
    def get_summary(self) -> dict[str, Any]:
        """Get summary of journal information."""
        return {
            "table": f"{self.table_library}.{self.table_name}",
            "journaled": self.is_journaled,
            "journal": f"{self.journal_library}.{self.journal_name}" if self.journal_library and self.journal_name else None,
            "journal_receiver": f"{self.journal_receiver_library}.{self.journal_receiver_name}" if self.journal_receiver_library and self.journal_receiver_name else None,
            "entry_range": {
                "oldest_sequence": self.oldest_entry_sequence,
                "newest_sequence": self.newest_entry_sequence,
                "oldest_time": self.oldest_entry_timestamp,
                "newest_time": self.newest_entry_timestamp,
            } if self.is_journaled else None,
        }


class JournalReceiverInfo(BaseModel):
    """Journal receiver information."""

    receiver_library: str
    receiver_name: str
    attached: bool = False
    created: str | None = None
    entries: int | None = None
    size: int | None = None
