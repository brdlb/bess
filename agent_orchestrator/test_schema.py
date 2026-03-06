import json
from langchain_core.pydantic_v1 import BaseModel, Field
from typing import Optional, List

class AskUserSchema(BaseModel):
    question: str = Field(description="The question to ask the user.")
    options: Optional[List[str]] = Field(default=None, description="Optional list of strings for multiple choice answers.")

print(json.dumps(AskUserSchema.schema(), indent=2))
