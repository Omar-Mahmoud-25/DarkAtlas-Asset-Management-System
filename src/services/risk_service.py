import json
from src.core.config import get_config
from src.services.assets_service import AssetsService
from src.services.relationships_service import RelationshipsService
from src.models.schema import AssetGraphResponse
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

class RiskAssessment(BaseModel):
    score: int = Field(description="Risk score from 0 to 100, where 100 is highest risk.")
    summary: str = Field(description="A brief summary explaining the cybersecurity risk.")

class RiskService:
    def __init__(self, db_session):
        self.assets_service = AssetsService(db_session)
        self.relationships_service = RelationshipsService(db_session)
        self.config = get_config()

    def evaluate_asset_risk(self, asset_id: str, model_name: str | None = None) -> dict | None:
        if not self.config.OLLAMA_API_KEY:
            raise ValueError("OLLAMA_API_KEY is not configured. Risk scoring is disabled.")

        # Get the asset graph to provide context (shows relationships and metadata like expired certs)
        graph = self.relationships_service.get_asset_graph(asset_id)
        if not graph:
            return None

        selected_model = model_name or self.config.GEMINI_MODEL

        # Normalize model name: ensure it has the "models/" prefix
        if not selected_model.startswith("models/"):
            selected_model = f"models/{selected_model}"

        # Prepare the LLM using the specified Gemini model
        try:
            llm = ChatOllama(
                model=selected_model,
                base_url=self.config.OLLAMA_BASE_URL or "https://api.ollama.com",
                api_key=self.config.OLLAMA_API_KEY,
            )

        except Exception as e:
            raise ValueError(
                f"Failed to initialize model '{selected_model}'. "
                f"Please use a valid Gemini model name (e.g. 'gemini-2.5-flash', 'gemini-2.0-flash'). "
                f"Error: {e}"
            )

        structured_llm = llm.with_structured_output(RiskAssessment)

        prompt = PromptTemplate.from_template(
            "Analyze the cybersecurity risk for the following digital asset and its relationships.\n\n"
            "Asset details:\n{asset_json}\n\n"
            "Provide a risk score (0-100) and a brief summary of the potential risks (e.g., exposed ports, expired certificates, risky relationships).\n"
        )

        # Convert graph to JSON for the prompt
        asset_obj, parents_list, children_list = graph
        
        def _to_dict(a):
            return a.__dict__ | {"metadata": a.metadata_ or {}}
            
        graph_response = AssetGraphResponse.model_validate({
            "asset": _to_dict(asset_obj),
            "parents": [{"asset": _to_dict(p["asset"]), "relation_type": p["relation_type"]} for p in parents_list],
            "children": [{"asset": _to_dict(c["asset"]), "relation_type": c["relation_type"]} for c in children_list]
        })
        
        graph_data = graph_response.model_dump(mode="json")
        asset_json = json.dumps(graph_data, indent=2)

        chain = prompt | structured_llm

        try:
            result = chain.invoke({"asset_json": asset_json})
            return {
                "score": result.score,
                "summary": result.summary
            }
        except Exception as e:
            raise RuntimeError(f"Failed to generate risk assessment: {str(e)}")
