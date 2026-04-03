from pydantic import BaseModel, Field

from bible_mcp.domain.metadata import ENTITY_TYPES, RELATION_TYPES


class MetadataEntity(BaseModel):
    slug: str
    display_name: str
    description: str | None = None


class PlaceRecord(BaseModel):
    slug: str
    display_name: str
    latitude: float | None = None
    longitude: float | None = None


class EntityAliasRecord(BaseModel):
    entity_type: str
    entity_slug: str
    alias: str


class EntityVerseLinkRecord(BaseModel):
    entity_type: str
    entity_slug: str
    reference: str


class EntityRelationshipRecord(BaseModel):
    source_type: str
    source_slug: str
    relation_type: str
    target_type: str
    target_slug: str
    is_primary: bool = False
    note: str | None = None


class MetadataBundle(BaseModel):
    people: list[MetadataEntity] = Field(default_factory=list)
    places: list[PlaceRecord] = Field(default_factory=list)
    events: list[MetadataEntity] = Field(default_factory=list)
    aliases: list[EntityAliasRecord] = Field(default_factory=list)
    entity_verse_links: list[EntityVerseLinkRecord] = Field(default_factory=list)
    relationships: list[EntityRelationshipRecord] = Field(default_factory=list)
