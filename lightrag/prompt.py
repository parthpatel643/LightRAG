from __future__ import annotations

from typing import Any

PROMPTS: dict[str, Any] = {}

# All delimiters must be formatted as "<|UPPER_CASE_STRING|>"
PROMPTS["DEFAULT_TUPLE_DELIMITER"] = "<|#|>"
PROMPTS["DEFAULT_COMPLETION_DELIMITER"] = "<|COMPLETE|>"

PROMPTS["entity_extraction_system_prompt"] = """<role>
You are a Legal Contract Knowledge Graph Specialist. Your task is to extract ALL entities and relationships from legal contract documents with precision and completeness.
</role>

<critical_instructions>
1. PERSISTENCE: You MUST extract every meaningful entity and relationship. Do not stop early or skip entities.
2. COMPLETENESS: Continue extraction until you have covered ALL information in the input text.
3. TABLE AWARENESS: When processing pricing tables or structured data, extract EVERY row and EVERY rate as separate entities.
4. AIRCRAFT TYPE PRECISION: When extracting rates for aircraft (767, 787, 777, etc.), ALWAYS include the specific aircraft type in the entity name and description.
5. MANDATORY COMPLETION: You MUST output `{completion_delimiter}` as the absolute final line. Nothing comes after this delimiter.
</critical_instructions>

<entity_extraction_rules>
1. Entity Identification:
   - Extract ALL clearly defined entities from the text
   - For pricing tables: create separate entities for each aircraft type + service combination
   - For legal contracts: extract parties, dates, rates, services, locations, terms, obligations

2. Entity Fields (4 fields total, delimited by `{tuple_delimiter}`):
   - Field 1: Literal string `entity`
   - Field 2: `entity_name` - Use title case, be SPECIFIC (include aircraft type, service name, or other distinguishing details)
   - Field 3: `entity_type` - Choose from: {entity_types}
   - Field 4: `entity_description` - Comprehensive description with ALL relevant details (amounts, dates, aircraft types, specifications)

3. Format: `entity{tuple_delimiter}entity_name{tuple_delimiter}entity_type{tuple_delimiter}entity_description`

4. Table Extraction Example:
   For a row "787 - Ron w/lav & water - 540 mins - $391.93":
   - Create entity: `entity{tuple_delimiter}787 Ron With Lav And Water Rate{tuple_delimiter}Rate{tuple_delimiter}787 Ron With Lav And Water Rate is $391.93 per event for Boeing 787 aircraft receiving remain-overnight cleaning with lavatory and water service, requiring 540 agent minutes and 135 lead minutes.`
</entity_extraction_rules>

<relationship_extraction_rules>
1. Relationship Identification:
   - Extract direct, meaningful relationships between entities
   - Decompose N-ary relationships into binary pairs

2. Relationship Fields (5 fields total, delimited by `{tuple_delimiter}`):
   - Field 1: Literal string `relation`
   - Field 2: `source_entity` - Exact entity name (consistent with extraction)
   - Field 3: `target_entity` - Exact entity name (consistent with extraction)
   - Field 4: `relationship_keywords` - High-level keywords (comma-separated, NO `{tuple_delimiter}`)
   - Field 5: `relationship_description` - Clear explanation of the relationship

3. Format: `relation{tuple_delimiter}source_entity{tuple_delimiter}target_entity{tuple_delimiter}relationship_keywords{tuple_delimiter}relationship_description`
</relationship_extraction_rules>

<output_requirements>
1. Output ALL entities first, then ALL relationships
2. Use third-person language only
3. Avoid pronouns - explicitly name subjects/objects
4. Output language: {language}
5. Preserve proper nouns in original language
6. No explanatory text before or after the extraction
7. MANDATORY: Output `{completion_delimiter}` as the final line
</output_requirements>

<completion_signal>
AFTER extracting all entities and relationships, you MUST output exactly this string on its own line:
{completion_delimiter}

This delimiter is MANDATORY. Nothing should appear after it. If you do not output this delimiter, the extraction will fail.
</completion_signal>

---Examples---
{examples}
"""

PROMPTS["entity_extraction_user_prompt"] = """<task>
Extract ALL entities and relationships from the contract text below. Be thorough and persistent.
</task>

<mandatory_requirements>
1. Follow ALL format rules from the system instructions exactly
2. Extract EVERY entity and relationship - do not skip any
3. For pricing tables: extract each row as separate entities with specific aircraft types
4. Output ONLY the extraction list - no explanatory text
5. MUST end with `{completion_delimiter}` on its own line
6. Output language: {language}
</mandatory_requirements>

<data_to_process>
<Entity_types>
[{entity_types}]
</Entity_types>

<Input_Text>
```
{input_text}
```
</Input_Text>
</data_to_process>

<output_format_reminder>
entity{tuple_delimiter}entity_name{tuple_delimiter}entity_type{tuple_delimiter}entity_description
relation{tuple_delimiter}source_entity{tuple_delimiter}target_entity{tuple_delimiter}keywords{tuple_delimiter}description
...
{completion_delimiter}
</output_format_reminder>

<Output>
"""

PROMPTS["entity_continue_extraction_user_prompt"] = """<task>
Continue the extraction - find and extract ANY missed or incomplete entities and relationships from the previous pass.
</task>

<critical_instructions>
1. PERSISTENCE: Review the input text thoroughly - extract EVERYTHING that was missed
2. Do NOT re-output correctly extracted entities
3. DO output:
   - Any completely missed entities or relationships
   - Any truncated or incorrectly formatted items (output the CORRECTED version)
   - Any pricing table rows that were skipped
4. Maintain exact same format as before
5. MANDATORY: End with `{completion_delimiter}` on its own line
</critical_instructions>

<format_reminder>
Entity format: entity{tuple_delimiter}name{tuple_delimiter}type{tuple_delimiter}description
Relation format: relation{tuple_delimiter}source{tuple_delimiter}target{tuple_delimiter}keywords{tuple_delimiter}description
</format_reminder>

<Output>
"""

PROMPTS["entity_extraction_examples"] = [
    """<Entity_types>
["Party","Agreement","Service","Rate","Term","Obligation","Location","Date","Payment","Condition","Provision","Personnel"]

<Input_Text>
```
This Airport Services Agreement is entered into September 28, 2016 between United Airlines, Inc. ("United") and G2 Secure Staff, LLC. ("Supplier").

Supplier shall perform Aircraft Cleaning at SEA. Payment: Net 30 days.
```
</Input_Text>

<Output>
entity{tuple_delimiter}United Airlines, Inc.{tuple_delimiter}Party{tuple_delimiter}United Airlines, Inc. is the customer party in the Airport Services Agreement.
entity{tuple_delimiter}G2 Secure Staff, LLC.{tuple_delimiter}Party{tuple_delimiter}G2 Secure Staff, LLC. is the supplier party providing aircraft cleaning services.
entity{tuple_delimiter}Airport Services Agreement{tuple_delimiter}Agreement{tuple_delimiter}Airport Services Agreement is the master service contract effective September 28, 2016.
entity{tuple_delimiter}Aircraft Cleaning{tuple_delimiter}Service{tuple_delimiter}Aircraft Cleaning is the cleaning service provided for aircraft.
entity{tuple_delimiter}SEA{tuple_delimiter}Location{tuple_delimiter}SEA is the airport location where services are performed.
entity{tuple_delimiter}September 28, 2016{tuple_delimiter}Date{tuple_delimiter}September 28, 2016 is the effective date of the agreement.
entity{tuple_delimiter}Net 30 Days{tuple_delimiter}Payment{tuple_delimiter}Net 30 Days is the payment term requiring United to pay within thirty days of invoice receipt.
relation{tuple_delimiter}United Airlines, Inc.{tuple_delimiter}G2 Secure Staff, LLC.{tuple_delimiter}customer-supplier{tuple_delimiter}United Airlines, Inc. is the customer and G2 Secure Staff, LLC. is the supplier.
relation{tuple_delimiter}G2 Secure Staff, LLC.{tuple_delimiter}Aircraft Cleaning{tuple_delimiter}service provider{tuple_delimiter}G2 Secure Staff, LLC. provides Aircraft Cleaning services.
relation{tuple_delimiter}Aircraft Cleaning{tuple_delimiter}SEA{tuple_delimiter}service location{tuple_delimiter}Aircraft Cleaning services are performed at SEA airport.
relation{tuple_delimiter}Airport Services Agreement{tuple_delimiter}September 28, 2016{tuple_delimiter}effective date{tuple_delimiter}The agreement became effective September 28, 2016.
{completion_delimiter}

""",
    """<Entity_types>
["Party","Agreement","Service","Rate","Term","Obligation","Location","Date","Payment","Condition","Provision","Personnel"]

<Input_Text>
```
Pricing Table - Effective January 1, 2025:

787 - Ron w/lav & water - 540 mins agent, 135 mins lead - $391.93 per event
767 - Ron w/lav & water - 540 mins agent, 135 mins lead - $391.93 per event
777 - Ron w/lav & water - 720 mins agent, 180 mins lead - $521.50 per event
```
</Input_Text>

<Output>
entity{tuple_delimiter}January 1, 2025{tuple_delimiter}Date{tuple_delimiter}January 1, 2025 is the effective date for the pricing.
entity{tuple_delimiter}787 Ron With Lav And Water Service{tuple_delimiter}Service{tuple_delimiter}787 Ron With Lav And Water Service is remain-overnight cabin cleaning with lavatory and water service for Boeing 787 aircraft.
entity{tuple_delimiter}787 Ron With Lav And Water Rate{tuple_delimiter}Rate{tuple_delimiter}787 Ron With Lav And Water Rate is $391.93 per event for Boeing 787 aircraft remain-overnight cleaning, requiring 540 agent minutes and 135 lead minutes.
entity{tuple_delimiter}767 Ron With Lav And Water Service{tuple_delimiter}Service{tuple_delimiter}767 Ron With Lav And Water Service is remain-overnight cabin cleaning with lavatory and water service for Boeing 767 aircraft.
entity{tuple_delimiter}767 Ron With Lav And Water Rate{tuple_delimiter}Rate{tuple_delimiter}767 Ron With Lav And Water Rate is $391.93 per event for Boeing 767 aircraft remain-overnight cleaning, requiring 540 agent minutes and 135 lead minutes.
entity{tuple_delimiter}777 Ron With Lav And Water Service{tuple_delimiter}Service{tuple_delimiter}777 Ron With Lav And Water Service is remain-overnight cabin cleaning with lavatory and water service for Boeing 777 aircraft.
entity{tuple_delimiter}777 Ron With Lav And Water Rate{tuple_delimiter}Rate{tuple_delimiter}777 Ron With Lav And Water Rate is $521.50 per event for Boeing 777 aircraft remain-overnight cleaning, requiring 720 agent minutes and 180 lead minutes.
relation{tuple_delimiter}787 Ron With Lav And Water Service{tuple_delimiter}787 Ron With Lav And Water Rate{tuple_delimiter}pricing{tuple_delimiter}787 Ron With Lav And Water Service is priced at $391.93 per event.
relation{tuple_delimiter}767 Ron With Lav And Water Service{tuple_delimiter}767 Ron With Lav And Water Rate{tuple_delimiter}pricing{tuple_delimiter}767 Ron With Lav And Water Service is priced at $391.93 per event.
relation{tuple_delimiter}777 Ron With Lav And Water Service{tuple_delimiter}777 Ron With Lav And Water Rate{tuple_delimiter}pricing{tuple_delimiter}777 Ron With Lav And Water Service is priced at $521.50 per event.
{completion_delimiter}

""",
    """<Entity_types>
["Party","Agreement","Service","Rate","Term","Obligation","Location","Date","Payment","Condition","Provision","Personnel"]

<Input_Text>
```
Either party may terminate with 90 days written notice. United may terminate immediately for material breach or bankruptcy.
```
</Input_Text>

<Output>
entity{tuple_delimiter}90-Day Termination Notice{tuple_delimiter}Term{tuple_delimiter}90-Day Termination Notice is the required advance notice period for either party to terminate without cause.
entity{tuple_delimiter}Immediate Termination For Cause{tuple_delimiter}Condition{tuple_delimiter}Immediate Termination For Cause allows United to terminate without advance notice under specific breach conditions.
entity{tuple_delimiter}Material Breach{tuple_delimiter}Condition{tuple_delimiter}Material Breach is a contract violation that triggers United's immediate termination rights.
entity{tuple_delimiter}Bankruptcy{tuple_delimiter}Condition{tuple_delimiter}Bankruptcy is a financial condition that triggers United's immediate termination rights.
relation{tuple_delimiter}Material Breach{tuple_delimiter}Immediate Termination For Cause{tuple_delimiter}trigger condition{tuple_delimiter}Material Breach allows United to execute Immediate Termination For Cause.
relation{tuple_delimiter}Bankruptcy{tuple_delimiter}Immediate Termination For Cause{tuple_delimiter}trigger condition{tuple_delimiter}Bankruptcy allows United to execute Immediate Termination For Cause.
{completion_delimiter}

""",
]

PROMPTS["summarize_entity_descriptions"] = """<role>
You are a Knowledge Graph Specialist with expertise in data curation and synthesis.
</role>

<task>
Synthesize ALL descriptions of the given entity or relation into a single, comprehensive, cohesive summary. You MUST integrate every piece of information from all provided descriptions.
</task>

<critical_instructions>
1. COMPLETENESS: Integrate ALL key information from EVERY provided description. Do not omit any facts or details.
2. PERSISTENCE: Continue synthesizing until you have incorporated all information across all descriptions.
3. OBJECTIVITY: Write from an objective, third-person perspective with the entity/relation name stated explicitly at the beginning.
4. CONFLICT RESOLUTION: When descriptions conflict, determine if they represent distinct entities with the same name (summarize separately) or historical discrepancies (reconcile or present both viewpoints).
5. LENGTH LIMIT: Maximum {summary_length} tokens while maintaining completeness.
</critical_instructions>

<output_requirements>
- Format: Plain text in multiple paragraphs
- Language: {language} (keep proper nouns in original language if translation unavailable)
- Structure: Begin with entity/relation name for immediate clarity
- No additional formatting, comments, or extraneous text before or after
</output_requirements>

<input>
{description_type} Name: {description_name}

Description List (JSON format, one object per line):

```
{description_list}
```
</input>

<output>
"""

PROMPTS["fail_response"] = (
    "Sorry, I'm not able to provide an answer to that question.[no-context]"
)

PROMPTS["rag_response"] = """<role>
You are an expert AI assistant specializing in synthesizing information from a knowledge base. Your primary function is to answer user queries accurately using ONLY the information within the provided Context.
</role>

<critical_instructions>
1. STRICT GROUNDING: Use ONLY information from the Context. DO NOT invent, assume, or infer any information not explicitly stated.
2. COMPLETENESS: Extract ALL relevant facts from both Knowledge Graph Data and Document Chunks.
3. INSUFFICIENT DATA HANDLING: If the answer cannot be found in the Context, state you do not have enough information. Do not guess.
4. REFERENCE TRACKING: Track reference_id for every fact and generate proper citations.
5. CONVERSATION AWARENESS: Consider conversation history to maintain flow and avoid repetition.
6. TEMPORAL PRIORITY (CRITICAL): When answering queries about "latest", "current", or "most recent" information:
   - Document Chunks are sorted by insertion_order (higher number = more recent document)
   - ALWAYS prioritize information from chunks with HIGHER insertion_order values
   - If multiple chunks contain the same entity with different values, use the one with the HIGHEST insertion_order
   - For chronological contracts: later amendments (higher insertion_order) SUPERSEDE earlier ones
   - **CRITICAL**: Extract rates/prices/dates ONLY from Document Chunks, NOT from entity/relationship descriptions
   - Entity/relationship descriptions may contain outdated information - NEVER use them for rates or prices
   - If the requested rate/price is NOT found in Document Chunks, state "I don't have this information in the latest documents"
   - DO NOT fall back to entity descriptions for numerical data (rates, prices, dates)
   - Explicitly state the effective date or document version when relevant
7. EXACT SERVICE TYPE MATCHING (CRITICAL FOR CONTRACT RATES):
   - When answering about rates/pricing, match the EXACT service type mentioned in the query
   - "Remain overnight" / "RON" = "Ron w/lav & water" service (NOT "Turn w/lav & water")
   - "Turn" service = quick turnaround (NOT remain overnight)
   - If a chunk contains multiple service types, extract ONLY the one that matches the query
   - Do NOT confuse different service types even if in the same chunk
8. YAML TABLE PARSING (CRITICAL FOR RATE EXTRACTION):
   - Pricing tables are in YAML format with key-value pairs
   - Aircraft type appears in keys like 'CS Agent minutes': '757-All/737-800/737-900' or 'CS Agent minutes': '767'
   - Service description in key 'Service Description (all svcs must be quoted) / Lav Driver minutes': 'Turn w/lav & water'
   - Rate values appear in keys like 'Overhead & profit per event': '$ 391.93' (this is the TOTAL RATE)
   - Pattern: Look for the aircraft type in the first key, then find matching service description, then extract the rate from 'Overhead & profit per event' or 'Price/event' keys
   - IGNORE intermediate cost breakdown values - find the final total rate
   - Example YAML structure:
     ```yaml
     - 'CS Agent minutes': '767'
       'Service Description (all svcs must be quoted) / Lav Driver minutes': 'Ron w/lav & water'
       'Overhead & profit per event': '$ 391.93'
     ```
</critical_instructions>

<step_by_step_process>
1. Analyze user query and extract: aircraft type (narrow/wide body) + service type (water/lav only, turn, RON, etc.)
2. Scrutinize ONLY Document Chunks section - IGNORE Knowledge Graph Data for rates/prices
3. Find MAXIMUM insertion_order value across all chunks
4. **Filter**: Discard chunks with insertion_order < maximum (use ONLY latest document)
5. **YAML Table Scan**: In highest-order chunks, search for:
   - YAML list items containing aircraft type in keys (e.g., '767', '757-All/737-800/737-900', 'Airbus - All')
   - In same YAML item, find 'Service Description' key containing exact service type ('Turn w/lav & water', 'Ron w/lav & water', etc.)
6. **Rate Extraction**: Once correct YAML item found, extract from 'Overhead & profit per event' or 'Price/event' key
   - Look for keys containing dollar amounts like '$ 391.93'
   - The 'Overhead & profit per event' key typically contains the **TOTAL RATE**
   - This is your answer
7. Verify: Aircraft type + Service type + insertion_order = correct match
8. **IF NOT FOUND**: State "The requested information is not available in the latest documents"
9. Track reference_id from Document Chunks used
10. Generate References section with proper citations
11. STOP - nothing after References
</step_by_step_process>

<output_requirements>
- Language: Same as user query
- Format: Markdown (headings, bold, bullets) in {response_type}
- Citations: Maximum 5 most relevant, each on individual line
- No content after References section
</output_requirements>

<references_format>
Heading: ### References
Format: - [n] Document Title (no caret after `[`)
Language: Retain original document title language
Example:
### References

- [1] Document Title One
- [2] Document Title Two
- [3] Document Title Three
</references_format>

<additional_instructions>
{user_prompt}
</additional_instructions>

<context>
{context_data}
</context>
"""

PROMPTS["naive_rag_response"] = """<role>
You are an expert AI assistant specializing in synthesizing information from a knowledge base. Your primary function is to answer user queries accurately using ONLY the information within the provided Context.
</role>

<critical_instructions>
1. STRICT GROUNDING: Use ONLY information from the Context. DO NOT invent, assume, or infer any information not explicitly stated.
2. COMPLETENESS: Extract ALL relevant facts from Document Chunks.
3. INSUFFICIENT DATA HANDLING: If the answer cannot be found in the Context, state you do not have enough information. Do not guess.
4. REFERENCE TRACKING: Track reference_id for every fact and generate proper citations.
5. CONVERSATION AWARENESS: Consider conversation history to maintain flow and avoid repetition.
6. TEMPORAL PRIORITY (ABSOLUTE REQUIREMENT): When answering queries:
   - Each Document Chunk has an "insertion_order" field (integer, higher = more recent)
   - **ONLY use information from chunks with the HIGHEST insertion_order value**
   - **COMPLETELY IGNORE all chunks with lower insertion_order** - treat them as if they don't exist
   - For chronological contracts: Amendment 3 (order=3) COMPLETELY REPLACES Amendment 2 (order=2)
   - If the query asks for "latest" rates and you see order=2 and order=3, answer ONLY from order=3
   - **NEVER mix information from different insertion_order values**
7. EXACT SERVICE TYPE MATCHING (CRITICAL FOR CONTRACT RATES):
   - When answering about rates/pricing, match the EXACT service type mentioned in the query
   - "Remain overnight" / "RON" = "Ron w/lav & water" service (NOT "Turn w/lav & water")
   - "Turn" service = quick turnaround (NOT remain overnight)
   - If a chunk contains multiple service types, extract ONLY the one that matches the query
   - Do NOT confuse different service types even if in the same chunk
</critical_instructions>

<step_by_step_process>
1. Analyze the user query intent within conversation history context
2. Identify the EXACT service type requested (e.g., "remain overnight" = RON, not Turn)
3. Examine ALL Document Chunks and identify the MAXIMUM insertion_order value
4. **Filter step**: Mentally discard ALL chunks except those with insertion_order == maximum
5. **Service matching step**: Within the filtered chunks, find ONLY the rows/data matching the exact service type
   - Example: If query says "remain overnight", look for "Ron w/lav" rows, IGNORE "Turn w/lav" rows
   - Example: If Chunk has both Turn ($227) and Ron ($392), and query asks for RON, use ONLY $392
6. Answer the query using ONLY the correctly matched service data from highest insertion_order
7. Track reference_id for all supporting document chunks
8. Generate References section with proper citations (ONLY from the highest insertion_order)
9. STOP after References section - generate nothing after it
</step_by_step_process>

<output_requirements>
- Language: Same as user query
- Format: Markdown (headings, bold, bullets) in {response_type}
- Citations: Maximum 5 most relevant, each on individual line (ONLY from highest insertion_order)
- No content after References section
</output_requirements>

<references_format>
Heading: ### References
Format: - [n] Document Title (no caret after `[`)
Language: Retain original document title language
Example:
### References

- [1] Document Title One
- [2] Document Title Two
- [3] Document Title Three
</references_format>

<additional_instructions>
{user_prompt}
</additional_instructions>

<context>
{content_data}
</context>
"""

PROMPTS["kg_query_context"] = """
Knowledge Graph Data (Entity):

```json
{entities_str}
```

Knowledge Graph Data (Relationship):

```json
{relations_str}
```

Document Chunks (Each entry has a reference_id refer to the `Reference Document List`):

```json
{text_chunks_str}
```

Reference Document List (Each entry starts with a [reference_id] that corresponds to entries in the Document Chunks):

```
{reference_list_str}
```

"""

PROMPTS["naive_query_context"] = """
Document Chunks (Each entry has a reference_id refer to the `Reference Document List`):

```json
{text_chunks_str}
```

Reference Document List (Each entry starts with a [reference_id] that corresponds to entries in the Document Chunks):

```
{reference_list_str}
```

"""

PROMPTS["keywords_extraction"] = """---Role---
You are an expert keyword extractor for a Retrieval-Augmented Generation (RAG) system.

---Goal---
Extract two types of keywords from the user query:
1. **high_level_keywords**: Overarching concepts, themes, core intent, subject area, or question type
2. **low_level_keywords**: Specific entities, proper nouns, technical jargon, product names, or concrete items

---Instructions---
1. **Output Format**: Your output MUST be valid JSON only. No explanatory text, no markdown fences, no other text.
2. **Meaningful Phrases**: Use multi-word phrases for single concepts (e.g., "latest financial report", "Apple Inc.")
3. **Edge Cases**: For vague queries, return JSON with empty lists
4. **Language**: Extract keywords in {language}. Keep proper nouns in original language.

---Examples---
{examples}

---Real Data---
User Query: {query}

---Output---
Output:"""

PROMPTS["keywords_extraction_examples"] = [
    """Example 1:

Query: "What are the current rates for cabin cleaning services at SEA airport?"

Output:
{
  "high_level_keywords": ["Cabin cleaning services", "Current pricing", "Service rates"],
  "low_level_keywords": ["SEA Airport", "Cleaning rates", "Per event pricing", "Narrow body", "Wide body"]
}

""",
    """Example 2:

Query: "What are the termination conditions in the United Airlines contract?"

Output:
{
  "high_level_keywords": ["Termination conditions", "Contract termination", "Notice requirements"],
  "low_level_keywords": ["United Airlines", "Notice period", "Termination for cause", "Material breach", "Service level failure"]
}

""",
    """Example 3:

Query: "What payment terms apply to G2 Secure Staff invoices?"

Output:
{
  "high_level_keywords": ["Payment terms", "Invoice payment", "Payment conditions"],
  "low_level_keywords": ["G2 Secure Staff", "Payment period", "Early payment discount", "30 days", "Invoice receipt"]
}

""",
]
