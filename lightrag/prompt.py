from __future__ import annotations

from typing import Any

PROMPTS: dict[str, Any] = {}

# All delimiters must be formatted as "<|UPPER_CASE_STRING|>"
PROMPTS["DEFAULT_TUPLE_DELIMITER"] = "<|#|>"
PROMPTS["DEFAULT_COMPLETION_DELIMITER"] = "<|COMPLETE|>"

PROMPTS["entity_extraction_system_prompt"] = """---Role---
You are a Knowledge Graph Specialist responsible for extracting entities and relationships from the input text.

---Instructions---
1.  **Entity Extraction & Output:**
    *   **Identification:** Identify clearly defined and meaningful entities in the input text. **IMPORTANT:** Extract entities from ALL formats including narrative text, tables, lists, YAML, JSON, and other structured data.
        *   **For Tables/Structured Data:** Extract service items, aircraft types, rate names, and other key elements as separate entities even if presented in tabular rows or key-value pairs.
    *   **Domain Alignment (Aviation Procurement):** When the input includes ground handling agreements, catering contracts, fuel service agreements, or SGHA-like terms, treat service items, aircraft types, vendors, rates, SLAs, penalties, equipment requirements, and contract terms as candidate entities. Preserve currency symbols (e.g., `$`, `€`), units (e.g., `per event`, `per turn`, `per gallon`, `minutes`), aircraft designators (e.g., `B787`), and timing exactly as written.
        *   **Example:** In a pricing table row "Boeing 787 | RON w/lav & water | $540", extract entities: "Boeing 787" (Aircraft), "RON w/lav & water" (Service), "$540" (Rate).
    *   **Entity Details:** For each identified entity, extract the following information:
        *   `entity_name`: The name of the entity. If the entity name is case-insensitive, capitalize the first letter of each significant word (title case). Ensure **consistent naming** across the entire extraction process.
    *   `entity_type`: Categorize the entity using one of the following types: `{entity_types}` (case-insensitive) and output the type in lowercase. If none of the provided entity types apply, do not add a new entity type; classify it as `other`.
        *   `entity_description`: Provide a concise yet comprehensive description of the entity's attributes and activities, based *solely* on the information present in the input text.
    *   **Output Format - Entities:** Output a total of 4 fields for each entity, delimited by `{tuple_delimiter}`, on a single line. The first field *must* be the literal string `entity`.
        *   Format: `entity{tuple_delimiter}entity_name{tuple_delimiter}entity_type{tuple_delimiter}entity_description`

2.  **Relationship Extraction & Output:**
    *   **Identification:** Identify direct, clearly stated, and meaningful relationships between previously extracted entities.
    *   **N-ary Relationship Decomposition:** If a single statement describes a relationship involving more than two entities (an N-ary relationship), decompose it into multiple binary (two-entity) relationship pairs for separate description.
        *   **Example:** For "Alice, Bob, and Carol collaborated on Project X," extract binary relationships such as "Alice collaborated with Project X," "Bob collaborated with Project X," and "Carol collaborated with Project X," or "Alice collaborated with Bob," based on the most reasonable binary interpretations.
    *   **Relationship Details:** For each binary relationship, extract the following fields:
        *   `source_entity`: The name of the source entity. Ensure **consistent naming** with entity extraction. Capitalize the first letter of each significant word (title case) if the name is case-insensitive.
        *   `target_entity`: The name of the target entity. Ensure **consistent naming** with entity extraction. Capitalize the first letter of each significant word (title case) if the name is case-insensitive.
        *   `relationship_keywords`: One or more high-level keywords summarizing the overarching nature, concepts, or themes of the relationship. Multiple keywords within this field must be separated by a comma `,`. **DO NOT use `{tuple_delimiter}` for separating multiple keywords within this field.**
        *   `relationship_description`: A concise explanation of the nature of the relationship between the source and target entities, providing a clear rationale for their connection.
  *   **Domain Keyword Taxonomy (Examples):** Prefer aviation procurement terms such as `service provision`, `rate applicability`, `sla compliance`, `penalty trigger`, `equipment requirement`, `contract enforcement`, `station location`, `aircraft type coverage`, `turnaround time`, `on-time performance`.
    *   **Output Format - Relationships:** Output a total of 5 fields for each relationship, delimited by `{tuple_delimiter}`, on a single line. The first field *must* be the literal string `relation`.
        *   Format: `relation{tuple_delimiter}source_entity{tuple_delimiter}target_entity{tuple_delimiter}relationship_keywords{tuple_delimiter}relationship_description`

3.  **Delimiter Usage Protocol:**
    *   The `{tuple_delimiter}` is a complete, atomic marker and **must not be filled with content**. It serves strictly as a field separator.
    *   **Incorrect Example:** `entity{tuple_delimiter}Tokyo<|location|>Tokyo is the capital of Japan.`
    *   **Correct Example:** `entity{tuple_delimiter}Tokyo{tuple_delimiter}location{tuple_delimiter}Tokyo is the capital of Japan.`

4.  **Relationship Direction & Duplication:**
    *   Treat all relationships as **undirected** unless explicitly stated otherwise. Swapping the source and target entities for an undirected relationship does not constitute a new relationship.
    *   Avoid outputting duplicate relationships.

5.  **Output Order & Prioritization:**
    *   Output all extracted entities first, followed by all extracted relationships.
    *   Within the list of relationships, prioritize and output those relationships that are **most significant** to the core meaning of the input text first.
  *   In aviation agreements, prioritize service-to-aircraft coverage, service-to-rate pricing, SLA-to-service compliance, and penalty triggers.

6.  **Context & Objectivity:**
    *   Ensure all entity names and descriptions are written in the **third person**.
    *   Explicitly name the subject or object; **avoid using pronouns** such as `this article`, `this paper`, `our company`, `I`, `you`, and `he/she`.
  *   Do not infer totals, convert currencies, or derive unmentioned metrics (e.g., effective hourly rates). Only reflect information explicitly stated in the text.

7.  **Language & Proper Nouns:**
    *   The entire output (entity names, keywords, and descriptions) must be written in `{language}`.
    *   Proper nouns (e.g., personal names, place names, organization names) should be retained in their original language if a proper, widely accepted translation is not available or would cause ambiguity.
  *   Preserve numbers, percentages, currency symbols, and measurement units exactly as they appear; do not normalize or convert them.

8.  **Completion Signal:** Output the literal string `{completion_delimiter}` only after all entities and relationships, following all criteria, have been completely extracted and outputted.

---Examples---
{examples}
"""

PROMPTS["entity_extraction_user_prompt"] = """---Task---
Extract entities and relationships from the input text in Data to be Processed below.

---Instructions---
1.  **Strict Adherence to Format:** Strictly adhere to all format requirements for entity and relationship lists, including output order, field delimiters, and proper noun handling, as specified in the system prompt.
2.  **Output Content Only:** Output *only* the extracted list of entities and relationships. Do not include any introductory or concluding remarks, explanations, or additional text before or after the list.
3.  **Completion Signal:** Output `{completion_delimiter}` as the final line after all relevant entities and relationships have been extracted and presented.
4.  **Output Language:** Ensure the output language is {language}. Proper nouns (e.g., personal names, place names, organization names) must be kept in their original language and not translated.
5.  **Domain & Numeric Fidelity:** Prefer aviation procurement terminology (e.g., service, rate, SLA, penalty, equipment, contract term, aircraft type). Preserve numbers, percentages, currency symbols, and measurement units exactly as written; do not normalize, convert, or infer totals.
6.  **Type Normalization:** Match `{entity_types}` case-insensitively but output `entity_type` in lowercase. Use `other` when no type applies.
7.  **Relationship Keywords:** Prefer domain keywords such as `service provision`, `rate applicability`, `sla compliance`, `penalty trigger`, `equipment requirement`, `contract enforcement`, `aircraft type coverage`, `turnaround time`, `on-time performance`.

---Data to be Processed---
<Entity_types>
[{entity_types}]

<Input Text>
```
{input_text}
```

<Output>
"""

PROMPTS["entity_continue_extraction_user_prompt"] = """---Task---
Based on the last extraction task, identify and extract any **missed or incorrectly formatted** entities and relationships from the input text.

---Instructions---
1.  **Strict Adherence to System Format:** Strictly adhere to all format requirements for entity and relationship lists, including output order, field delimiters, and proper noun handling, as specified in the system instructions.
2.  **Focus on Corrections/Additions:**
    *   **Do NOT** re-output entities and relationships that were **correctly and fully** extracted in the last task.
    *   If an entity or relationship was **missed** in the last task, extract and output it now according to the system format.
    *   If an entity or relationship was **truncated, had missing fields, or was otherwise incorrectly formatted** in the last task, re-output the *corrected and complete* version in the specified format.
3.  **Output Format - Entities:** Output a total of 4 fields for each entity, delimited by `{tuple_delimiter}`, on a single line. The first field *must* be the literal string `entity`.
4.  **Output Format - Relationships:** Output a total of 5 fields for each relationship, delimited by `{tuple_delimiter}`, on a single line. The first field *must* be the literal string `relation`.
5.  **Output Content Only:** Output *only* the extracted list of entities and relationships. Do not include any introductory or concluding remarks, explanations, or additional text before or after the list.
6.  **Completion Signal:** Output `{completion_delimiter}` as the final line after all relevant missing or corrected entities and relationships have been extracted and presented.
7.  **Output Language:** Ensure the output language is {language}. Proper nouns (e.g., personal names, place names, organization names) must be kept in their original language and not translated.
8.  **Domain & Numeric Fidelity:** Prefer aviation procurement terminology. Preserve numbers, percentages, currency symbols, and measurement units exactly as written; do not normalize, convert, or infer totals.
9.  **Type Normalization:** Match `{entity_types}` case-insensitively but output `entity_type` in lowercase. Use `other` when no type applies.
10. **Relationship Keywords:** Prefer domain keywords such as `service provision`, `rate applicability`, `sla compliance`, `penalty trigger`, `equipment requirement`, `contract enforcement`, `aircraft type coverage`, `turnaround time`, `on-time performance`.

<Output>
"""

PROMPTS["entity_extraction_examples"] = [
    """<Entity_types>
["Person","Organization","Location","Event","Service","Aircraft","Rate","Vendor","SLA","Penalty","ContractTerm","Equipment"]

<Input Text>
```
Airline Ground Services Agreement - Seattle (SEA) Station

Service Provider: G2 Secure Staff LLC shall provide aircraft appearance and janitorial services for all Boeing 787 aircraft operating at SEA.

Pricing Schedule:
- Boeing 787 RON (Remain Overnight) with lavatory and water service: $384.08 per event
- Turn cleaning with lavatory service: $125.50 per turn
- Deep clean service: $950.00 per event, scheduled quarterly

Service Level Agreement:
- RON cleaning must be completed within 4 hours of aircraft arrival
- Turn cleaning turnaround time: 35 minutes maximum
- On-time performance requirement: 98% monthly average

Penalties:
- Delay beyond SLA: $50 per 15-minute increment
- Monthly performance below 98%: $500 penalty per percentage point
- Repeat violations may result in contract termination per Article 12.3

Equipment Requirements:
- Ground Power Unit (GPU) must be available 24/7
- Potable water trucks must have 50-foot hoses for 787 operations
```

<Output>
entity{tuple_delimiter}G2 Secure Staff LLC{tuple_delimiter}vendor{tuple_delimiter}G2 Secure Staff LLC is the service provider for aircraft appearance and janitorial services at Seattle station.
entity{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft{tuple_delimiter}Boeing 787 is a widebody aircraft type requiring specialized ground handling and cleaning services.
entity{tuple_delimiter}Seattle Station{tuple_delimiter}location{tuple_delimiter}Seattle Station (SEA) is the airport location where ground services are provided.
entity{tuple_delimiter}RON Cleaning{tuple_delimiter}service{tuple_delimiter}RON (Remain Overnight) cleaning is a comprehensive aircraft cleaning service performed on aircraft staying overnight, including lavatory and water service.
entity{tuple_delimiter}Turn Cleaning{tuple_delimiter}service{tuple_delimiter}Turn cleaning is a quick turnaround cleaning service performed between flights with lavatory service.
entity{tuple_delimiter}Deep Clean{tuple_delimiter}service{tuple_delimiter}Deep clean is a comprehensive quarterly cleaning service for aircraft.
entity{tuple_delimiter}$384.08 RON Rate{tuple_delimiter}rate{tuple_delimiter}The rate for Boeing 787 RON cleaning with lavatory and water service is $384.08 per event.
entity{tuple_delimiter}$125.50 Turn Rate{tuple_delimiter}rate{tuple_delimiter}The rate for turn cleaning with lavatory service is $125.50 per turn.
entity{tuple_delimiter}4-Hour RON SLA{tuple_delimiter}sla{tuple_delimiter}The service level agreement requires RON cleaning to be completed within 4 hours of aircraft arrival.
entity{tuple_delimiter}35-Minute Turn SLA{tuple_delimiter}sla{tuple_delimiter}Turn cleaning must be completed within 35 minutes maximum turnaround time.
entity{tuple_delimiter}98% On-Time Requirement{tuple_delimiter}sla{tuple_delimiter}Service provider must maintain 98% monthly average on-time performance.
entity{tuple_delimiter}Delay Penalty{tuple_delimiter}penalty{tuple_delimiter}Delays beyond SLA incur a $50 penalty per 15-minute increment.
entity{tuple_delimiter}Performance Penalty{tuple_delimiter}penalty{tuple_delimiter}Monthly performance below 98% incurs a $500 penalty per percentage point below threshold.
entity{tuple_delimiter}Article 12.3{tuple_delimiter}contractterm{tuple_delimiter}Article 12.3 governs contract termination procedures for repeat violations.
entity{tuple_delimiter}Ground Power Unit{tuple_delimiter}equipment{tuple_delimiter}Ground Power Unit (GPU) is required equipment that must be available 24/7 for aircraft operations.
entity{tuple_delimiter}Potable Water Truck{tuple_delimiter}equipment{tuple_delimiter}Potable water trucks with 50-foot hoses are required for Boeing 787 water service operations.
relation{tuple_delimiter}G2 Secure Staff LLC{tuple_delimiter}Boeing 787{tuple_delimiter}service provision, ground handling{tuple_delimiter}G2 Secure Staff LLC provides aircraft appearance and janitorial services for Boeing 787 aircraft.
relation{tuple_delimiter}Boeing 787{tuple_delimiter}RON Cleaning{tuple_delimiter}aircraft service, cleaning requirement{tuple_delimiter}Boeing 787 aircraft receive RON cleaning service when remaining overnight.
relation{tuple_delimiter}RON Cleaning{tuple_delimiter}$384.08 RON Rate{tuple_delimiter}service pricing, cost structure{tuple_delimiter}RON cleaning service is priced at $384.08 per event.
relation{tuple_delimiter}RON Cleaning{tuple_delimiter}4-Hour RON SLA{tuple_delimiter}service requirement, time constraint{tuple_delimiter}RON cleaning must comply with the 4-hour completion SLA.
relation{tuple_delimiter}Turn Cleaning{tuple_delimiter}35-Minute Turn SLA{tuple_delimiter}service requirement, turnaround time{tuple_delimiter}Turn cleaning is subject to a 35-minute maximum turnaround SLA.
relation{tuple_delimiter}4-Hour RON SLA{tuple_delimiter}Delay Penalty{tuple_delimiter}compliance enforcement, financial consequence{tuple_delimiter}Failure to meet the 4-hour RON SLA triggers the delay penalty structure.
relation{tuple_delimiter}98% On-Time Requirement{tuple_delimiter}Performance Penalty{tuple_delimiter}performance measurement, penalty trigger{tuple_delimiter}Performance below 98% triggers the monthly performance penalty.
relation{tuple_delimiter}Performance Penalty{tuple_delimiter}Article 12.3{tuple_delimiter}escalation path, contract enforcement{tuple_delimiter}Repeat violations resulting in performance penalties may lead to contract termination under Article 12.3.
relation{tuple_delimiter}Ground Power Unit{tuple_delimiter}Boeing 787{tuple_delimiter}equipment requirement, aircraft support{tuple_delimiter}GPU must be available 24/7 to support Boeing 787 operations.
relation{tuple_delimiter}Potable Water Truck{tuple_delimiter}Boeing 787{tuple_delimiter}specialized equipment, aircraft-specific requirement{tuple_delimiter}Potable water trucks with 50-foot hoses are specifically required for Boeing 787 water service.
{completion_delimiter}

""",
    """<Entity_types>
["Person","Organization","Location","Event","Service","Aircraft","Rate","Vendor","SLA","Penalty","ContractTerm","Equipment","NaturalObject","Concept"]

<Input Text>
```
Fuel Service Agreement – John F. Kennedy International Airport (JFK)

Service Provider: SkyFuel Services Inc. shall provide into-plane fueling for Boeing 787 operations at JFK. Fuel type: Jet A-1.

Pricing Schedule:
- Throughput fee: $0.015 per gallon
- Call-out fee (off-hours): $95.00 per call-out

Service Level Agreement (SLA):
- Fueling start within 25 minutes of block-on
- Max fueling completion time: 45 minutes
- On-time performance requirement: 97% monthly average

Penalties:
- Delay beyond SLA: $100 per 10-minute increment
- Performance below 97%: $400 penalty per percentage point

Contract Terms:
- Appendix B.4 details dispute resolution for fueling delays

Equipment Requirements:
- Hydrant dispenser with differential pressure gauge must be available
- Bonding cable must be attached before fueling commences
```

<Output>
entity{tuple_delimiter}SkyFuel Services Inc.{tuple_delimiter}vendor{tuple_delimiter}SkyFuel Services Inc. is the service provider responsible for into-plane fueling at JFK for Boeing 787 operations.
entity{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft{tuple_delimiter}Boeing 787 is the aircraft type covered by the fueling service at JFK.
entity{tuple_delimiter}John F. Kennedy International Airport (JFK){tuple_delimiter}location{tuple_delimiter}JFK is the airport location where into-plane fueling services are provided.
entity{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}service{tuple_delimiter}Into-plane fueling involves delivering Jet A-1 fuel directly to the aircraft at the gate in accordance with the fueling agreement.
entity{tuple_delimiter}Jet A-1{tuple_delimiter}naturalobject{tuple_delimiter}Jet A-1 is the fuel type specified for Boeing 787 operations in the fueling agreement.
entity{tuple_delimiter}$0.015 Per Gallon Throughput Fee{tuple_delimiter}rate{tuple_delimiter}The throughput fee is $0.015 per gallon of fuel delivered.
entity{tuple_delimiter}$95.00 Call-Out Fee{tuple_delimiter}rate{tuple_delimiter}The call-out fee applies to off-hours fueling requests and is $95.00 per call-out.
entity{tuple_delimiter}25-Minute Start SLA{tuple_delimiter}sla{tuple_delimiter}Fueling must start within 25 minutes of block-on time.
entity{tuple_delimiter}45-Minute Completion SLA{tuple_delimiter}sla{tuple_delimiter}Fueling must be completed within 45 minutes.
entity{tuple_delimiter}97% On-Time Requirement{tuple_delimiter}sla{tuple_delimiter}The service provider must maintain a 97% monthly average on-time performance.
entity{tuple_delimiter}Delay Beyond SLA Penalty{tuple_delimiter}penalty{tuple_delimiter}Delays beyond the SLA incur a $100 penalty per 10-minute increment.
entity{tuple_delimiter}Performance Below 97% Penalty{tuple_delimiter}penalty{tuple_delimiter}Performance below 97% incurs a $400 penalty per percentage point below the threshold.
entity{tuple_delimiter}Appendix B.4{tuple_delimiter}contractterm{tuple_delimiter}Appendix B.4 describes dispute resolution procedures related to fueling delays.
entity{tuple_delimiter}Hydrant Dispenser{tuple_delimiter}equipment{tuple_delimiter}A hydrant dispenser equipped with a differential pressure gauge must be available for fueling operations.
entity{tuple_delimiter}Bonding Cable{tuple_delimiter}equipment{tuple_delimiter}A bonding cable must be attached prior to fueling to ensure safety.
relation{tuple_delimiter}SkyFuel Services Inc.{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}service provision{tuple_delimiter}SkyFuel Services Inc. provides into-plane fueling services.
relation{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft type coverage{tuple_delimiter}Into-plane fueling is performed for Boeing 787 operations.
relation{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}Jet A-1{tuple_delimiter}fuel type{tuple_delimiter}Into-plane fueling uses Jet A-1 fuel.
relation{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}$0.015 Per Gallon Throughput Fee{tuple_delimiter}rate applicability{tuple_delimiter}The throughput fee applies to fuel delivered during into-plane fueling.
relation{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}$95.00 Call-Out Fee{tuple_delimiter}rate applicability{tuple_delimiter}Off-hours fueling requests are subject to the call-out fee.
relation{tuple_delimiter}25-Minute Start SLA{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}sla compliance{tuple_delimiter}Fueling must start within 25 minutes of block-on.
relation{tuple_delimiter}45-Minute Completion SLA{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}turnaround time{tuple_delimiter}Fueling must be completed within 45 minutes.
relation{tuple_delimiter}Delay Beyond SLA Penalty{tuple_delimiter}25-Minute Start SLA{tuple_delimiter}penalty trigger{tuple_delimiter}Delays beyond the start SLA trigger the delay penalty.
relation{tuple_delimiter}Performance Below 97% Penalty{tuple_delimiter}97% On-Time Requirement{tuple_delimiter}penalty trigger{tuple_delimiter}Monthly performance below 97% triggers the performance penalty.
relation{tuple_delimiter}Appendix B.4{tuple_delimiter}Delay Beyond SLA Penalty{tuple_delimiter}contract enforcement{tuple_delimiter}Appendix B.4 governs dispute resolution for fueling delays and related penalties.
relation{tuple_delimiter}Hydrant Dispenser{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}equipment requirement{tuple_delimiter}A hydrant dispenser is required for fueling operations.
relation{tuple_delimiter}Bonding Cable{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}equipment requirement{tuple_delimiter}A bonding cable must be attached before fueling begins.
{completion_delimiter}

""",
    """<Entity_types>
["Person","Organization","Location","Event","Service","Aircraft","Rate","Vendor","SLA","Penalty","ContractTerm","Equipment","NaturalObject","Concept"]

<Input Text>
```
Catering Service Agreement – London Heathrow (LHR)

Service Provider: AeroCater Ltd shall provide catering uplift and waste removal for Boeing 787 and Airbus A350 operations at LHR.

Pricing Schedule:
- Meal uplift: $9.80 per passenger
- Special meal handling: $3.50 per special meal
- Waste removal: $85.00 per event
- Dry ice supply: $1.20 per kilogram
- Galley cart exchange: $12.00 per cart

Service Level Agreement (SLA):
- Uplift complete 40 minutes before STD
- Waste removal within 20 minutes of block-on
- Special meal confirmation 6 hours prior to STD
- On-time performance requirement: 98% monthly average

Penalties:
- Late uplift beyond SLA: $75 per 10-minute increment
- Missed special meal: $250 per flight
- Performance below 98%: $300 penalty per percentage point

Contract Terms:
- Schedule C Section 7 covers allergen handling procedures
- Annex D.2 governs waste segregation (recyclable vs general)

Equipment Requirements:
- Waste compactor must be available at the stand
- Galley carts must meet Atlas standard dimensions
- Dry ice gloves must be used when handling
```

<Output>
entity{tuple_delimiter}AeroCater Ltd{tuple_delimiter}vendor{tuple_delimiter}AeroCater Ltd is the service provider responsible for catering uplift and waste removal at LHR for Boeing 787 and Airbus A350 operations.
entity{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft{tuple_delimiter}Boeing 787 is an aircraft type covered by the catering and waste services.
entity{tuple_delimiter}Airbus A350{tuple_delimiter}aircraft{tuple_delimiter}Airbus A350 is an aircraft type covered by the catering and waste services.
entity{tuple_delimiter}London Heathrow (LHR){tuple_delimiter}location{tuple_delimiter}LHR is the airport location where catering uplift and waste removal services are provided.
entity{tuple_delimiter}Catering Uplift{tuple_delimiter}service{tuple_delimiter}Catering uplift involves loading meals and beverages onto aircraft in accordance with service requirements.
entity{tuple_delimiter}Waste Removal{tuple_delimiter}service{tuple_delimiter}Waste removal involves the collection and disposal of aircraft cabin waste following flights.
entity{tuple_delimiter}Special Meal Handling{tuple_delimiter}service{tuple_delimiter}Special meal handling covers confirmation and provision of meals with specific dietary requirements.
entity{tuple_delimiter}Galley Cart Exchange{tuple_delimiter}service{tuple_delimiter}Galley cart exchange involves replacing or swapping galley carts that meet Atlas standard dimensions.
entity{tuple_delimiter}Dry Ice{tuple_delimiter}naturalobject{tuple_delimiter}Dry ice is a consumable used for keeping catering items chilled and is supplied per kilogram.
entity{tuple_delimiter}$9.80 Meal Uplift Rate{tuple_delimiter}rate{tuple_delimiter}The rate for meal uplift is $9.80 per passenger.
entity{tuple_delimiter}$3.50 Special Meal Handling Rate{tuple_delimiter}rate{tuple_delimiter}The rate for special meal handling is $3.50 per special meal.
entity{tuple_delimiter}$85.00 Waste Removal Rate{tuple_delimiter}rate{tuple_delimiter}The rate for waste removal is $85.00 per event.
entity{tuple_delimiter}$1.20/kg Dry Ice Rate{tuple_delimiter}rate{tuple_delimiter}The rate for dry ice supply is $1.20 per kilogram.
entity{tuple_delimiter}$12.00 Galley Cart Exchange Rate{tuple_delimiter}rate{tuple_delimiter}The rate for galley cart exchange is $12.00 per cart.
entity{tuple_delimiter}40-Minute Pre-STD Uplift SLA{tuple_delimiter}sla{tuple_delimiter}Catering uplift must be completed 40 minutes before scheduled time of departure (STD).
entity{tuple_delimiter}20-Minute Waste Removal SLA{tuple_delimiter}sla{tuple_delimiter}Waste removal must be completed within 20 minutes of block-on.
entity{tuple_delimiter}6-Hour Special Meal Confirmation SLA{tuple_delimiter}sla{tuple_delimiter}Special meals must be confirmed 6 hours prior to scheduled time of departure.
entity{tuple_delimiter}98% On-Time Requirement{tuple_delimiter}sla{tuple_delimiter}The service provider must maintain a 98% monthly average on-time performance.
entity{tuple_delimiter}Late Uplift Penalty{tuple_delimiter}penalty{tuple_delimiter}Late catering uplift beyond SLA incurs a $75 penalty per 10-minute increment.
entity{tuple_delimiter}Missed Special Meal Penalty{tuple_delimiter}penalty{tuple_delimiter}A missed special meal incurs a $250 penalty per flight.
entity{tuple_delimiter}Performance Penalty{tuple_delimiter}penalty{tuple_delimiter}Performance below 98% incurs a $300 penalty per percentage point below the threshold.
entity{tuple_delimiter}Schedule C Section 7{tuple_delimiter}contractterm{tuple_delimiter}Schedule C Section 7 covers allergen handling procedures for catering services.
entity{tuple_delimiter}Annex D.2{tuple_delimiter}contractterm{tuple_delimiter}Annex D.2 governs waste segregation requirements (recyclable vs general).
entity{tuple_delimiter}Waste Compactor{tuple_delimiter}equipment{tuple_delimiter}A waste compactor must be available at the stand for cabin waste processing.
entity{tuple_delimiter}Atlas Standard Galley Cart{tuple_delimiter}equipment{tuple_delimiter}Galley carts must meet Atlas standard dimensions.
entity{tuple_delimiter}Dry Ice Gloves{tuple_delimiter}equipment{tuple_delimiter}Dry ice gloves must be used when handling dry ice for safety.
relation{tuple_delimiter}AeroCater Ltd{tuple_delimiter}Catering Uplift{tuple_delimiter}service provision{tuple_delimiter}AeroCater Ltd provides catering uplift services.
relation{tuple_delimiter}AeroCater Ltd{tuple_delimiter}Waste Removal{tuple_delimiter}service provision{tuple_delimiter}AeroCater Ltd provides waste removal services.
relation{tuple_delimiter}AeroCater Ltd{tuple_delimiter}Special Meal Handling{tuple_delimiter}service provision{tuple_delimiter}AeroCater Ltd manages special meal handling and confirmations.
relation{tuple_delimiter}Catering Uplift{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft type coverage{tuple_delimiter}Catering uplift is performed for Boeing 787 operations at LHR.
relation{tuple_delimiter}Catering Uplift{tuple_delimiter}Airbus A350{tuple_delimiter}aircraft type coverage{tuple_delimiter}Catering uplift is performed for Airbus A350 operations at LHR.
relation{tuple_delimiter}Catering Uplift{tuple_delimiter}$9.80 Meal Uplift Rate{tuple_delimiter}rate applicability{tuple_delimiter}Meal uplift is billed at $9.80 per passenger.
relation{tuple_delimiter}Special Meal Handling{tuple_delimiter}$3.50 Special Meal Handling Rate{tuple_delimiter}rate applicability{tuple_delimiter}Special meal handling is billed at $3.50 per special meal.
relation{tuple_delimiter}Waste Removal{tuple_delimiter}$85.00 Waste Removal Rate{tuple_delimiter}rate applicability{tuple_delimiter}Waste removal is billed at $85.00 per event.
relation{tuple_delimiter}Dry Ice{tuple_delimiter}$1.20/kg Dry Ice Rate{tuple_delimiter}rate applicability{tuple_delimiter}Dry ice supply is billed at $1.20 per kilogram.
relation{tuple_delimiter}Galley Cart Exchange{tuple_delimiter}$12.00 Galley Cart Exchange Rate{tuple_delimiter}rate applicability{tuple_delimiter}Galley cart exchange is billed at $12.00 per cart.
relation{tuple_delimiter}40-Minute Pre-STD Uplift SLA{tuple_delimiter}Catering Uplift{tuple_delimiter}sla compliance{tuple_delimiter}Catering uplift must be complete 40 minutes before STD.
relation{tuple_delimiter}20-Minute Waste Removal SLA{tuple_delimiter}Waste Removal{tuple_delimiter}turnaround time{tuple_delimiter}Waste removal must be completed within 20 minutes of block-on.
relation{tuple_delimiter}6-Hour Special Meal Confirmation SLA{tuple_delimiter}Special Meal Handling{tuple_delimiter}sla compliance{tuple_delimiter}Special meals must be confirmed 6 hours prior to STD.
relation{tuple_delimiter}Late Uplift Penalty{tuple_delimiter}40-Minute Pre-STD Uplift SLA{tuple_delimiter}penalty trigger{tuple_delimiter}Late uplift beyond the SLA triggers the late uplift penalty.
relation{tuple_delimiter}Missed Special Meal Penalty{tuple_delimiter}6-Hour Special Meal Confirmation SLA{tuple_delimiter}penalty trigger{tuple_delimiter}Failure to confirm special meals on time triggers the missed special meal penalty.
relation{tuple_delimiter}Performance Penalty{tuple_delimiter}98% On-Time Requirement{tuple_delimiter}penalty trigger{tuple_delimiter}Performance below 98% triggers the monthly performance penalty.
relation{tuple_delimiter}Schedule C Section 7{tuple_delimiter}Special Meal Handling{tuple_delimiter}contract enforcement{tuple_delimiter}Allergen handling procedures apply to special meal handling.
relation{tuple_delimiter}Annex D.2{tuple_delimiter}Waste Removal{tuple_delimiter}contract enforcement{tuple_delimiter}Waste segregation requirements apply to waste removal services.
relation{tuple_delimiter}Waste Compactor{tuple_delimiter}Waste Removal{tuple_delimiter}equipment requirement{tuple_delimiter}A waste compactor must be available for cabin waste processing.
relation{tuple_delimiter}Atlas Standard Galley Cart{tuple_delimiter}Galley Cart Exchange{tuple_delimiter}equipment requirement{tuple_delimiter}Galley carts must meet Atlas standard dimensions.
relation{tuple_delimiter}Dry Ice Gloves{tuple_delimiter}Catering Uplift{tuple_delimiter}equipment requirement{tuple_delimiter}Dry ice gloves must be used when handling dry ice during catering uplift.
{completion_delimiter}

""",
    """<Entity_types>
["Person","Organization","Location","Event","Service","Aircraft","Rate","Vendor","SLA","Penalty","ContractTerm","Equipment","NaturalObject","Concept"]

<Input Text>
```
Deicing Service Agreement – Denver International Airport (DEN)

Service Provider: FrostJet Services shall provide Type I deicing and Type IV anti-icing for Boeing 787 operations at DEN.

Pricing Schedule:
- Type I fluid application: $2.75 per gallon
- Type IV fluid application: $4.20 per gallon
- Call-out fee (off-hours): $180.00 per call-out
- Pad occupancy: $35.00 per 10-minute increment

Service Level Agreement (SLA):
- Deicing start within 15 minutes of request
- Max deicing completion time: 30 minutes
- Holdover time calculation per SAE tables
- On-time performance requirement: 97% monthly average

Penalties:
- Delay beyond SLA: $120 per 10-minute increment
- Incorrect holdover time computation: $500 per event
- Performance below 97%: $400 penalty per percentage point

Contract Terms:
- Exhibit E defines fluid dilution ratios and environmental discharge limits

Equipment Requirements:
- Heated spray rigs with viscosity monitors must be used
- Glycol recovery systems are required on the pad
- Safety cones and marshallers must be present during operations
```

<Output>
entity{tuple_delimiter}FrostJet Services{tuple_delimiter}vendor{tuple_delimiter}FrostJet Services is the provider of deicing and anti-icing services at DEN for Boeing 787 operations.
entity{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft{tuple_delimiter}Boeing 787 is the aircraft type covered by the deicing agreement.
entity{tuple_delimiter}Denver International Airport (DEN){tuple_delimiter}location{tuple_delimiter}DEN is the airport location where deicing services are provided.
entity{tuple_delimiter}Type I Deicing{tuple_delimiter}service{tuple_delimiter}Type I deicing involves applying heated fluid to remove frost, ice, and snow from aircraft surfaces.
entity{tuple_delimiter}Type IV Anti-Icing{tuple_delimiter}service{tuple_delimiter}Type IV anti-icing involves applying fluid to delay ice accretion after deicing.
entity{tuple_delimiter}Type I Fluid{tuple_delimiter}naturalobject{tuple_delimiter}Type I deicing fluid is used to remove contamination and is billed per gallon.
entity{tuple_delimiter}Type IV Fluid{tuple_delimiter}naturalobject{tuple_delimiter}Type IV anti-icing fluid is used to prevent re-accumulation and is billed per gallon.
entity{tuple_delimiter}$2.75 Type I Rate{tuple_delimiter}rate{tuple_delimiter}The application rate for Type I fluid is $2.75 per gallon.
entity{tuple_delimiter}$4.20 Type IV Rate{tuple_delimiter}rate{tuple_delimiter}The application rate for Type IV fluid is $4.20 per gallon.
entity{tuple_delimiter}$180.00 Call-Out Fee{tuple_delimiter}rate{tuple_delimiter}The off-hours call-out fee is $180.00 per call-out.
entity{tuple_delimiter}$35.00 Pad Occupancy Fee{tuple_delimiter}rate{tuple_delimiter}Pad occupancy is billed at $35.00 per 10-minute increment.
entity{tuple_delimiter}15-Minute Start SLA{tuple_delimiter}sla{tuple_delimiter}Deicing must start within 15 minutes of the service request.
entity{tuple_delimiter}30-Minute Completion SLA{tuple_delimiter}sla{tuple_delimiter}Deicing must be completed within 30 minutes.
entity{tuple_delimiter}Holdover Time Compliance{tuple_delimiter}sla{tuple_delimiter}Holdover time must be calculated according to SAE tables.
entity{tuple_delimiter}97% On-Time Requirement{tuple_delimiter}sla{tuple_delimiter}The provider must maintain a 97% monthly average on-time performance.
entity{tuple_delimiter}Delay Penalty{tuple_delimiter}penalty{tuple_delimiter}Delays beyond the SLA incur a $120 penalty per 10-minute increment.
entity{tuple_delimiter}Holdover Computation Penalty{tuple_delimiter}penalty{tuple_delimiter}Incorrect holdover time computation incurs a $500 penalty per event.
entity{tuple_delimiter}Performance Penalty{tuple_delimiter}penalty{tuple_delimiter}Performance below 97% incurs a $400 penalty per percentage point below the threshold.
entity{tuple_delimiter}Exhibit E{tuple_delimiter}contractterm{tuple_delimiter}Exhibit E defines fluid dilution ratios and environmental discharge limits for deicing operations.
entity{tuple_delimiter}Heated Spray Rig{tuple_delimiter}equipment{tuple_delimiter}A heated spray rig equipped with viscosity monitors must be used during deicing.
entity{tuple_delimiter}Glycol Recovery System{tuple_delimiter}equipment{tuple_delimiter}A glycol recovery system is required on the pad to collect runoff.
entity{tuple_delimiter}Safety Cones{tuple_delimiter}equipment{tuple_delimiter}Safety cones and marshallers must be present during deicing operations for safety.
relation{tuple_delimiter}FrostJet Services{tuple_delimiter}Type I Deicing{tuple_delimiter}service provision{tuple_delimiter}FrostJet Services provides Type I deicing.
relation{tuple_delimiter}FrostJet Services{tuple_delimiter}Type IV Anti-Icing{tuple_delimiter}service provision{tuple_delimiter}FrostJet Services provides Type IV anti-icing.
relation{tuple_delimiter}Type I Deicing{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft type coverage{tuple_delimiter}Type I deicing is performed for Boeing 787 operations.
relation{tuple_delimiter}Type IV Anti-Icing{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft type coverage{tuple_delimiter}Type IV anti-icing is performed for Boeing 787 operations.
relation{tuple_delimiter}Type I Deicing{tuple_delimiter}$2.75 Type I Rate{tuple_delimiter}rate applicability{tuple_delimiter}Type I fluid application is billed at $2.75 per gallon.
relation{tuple_delimiter}Type IV Anti-Icing{tuple_delimiter}$4.20 Type IV Rate{tuple_delimiter}rate applicability{tuple_delimiter}Type IV fluid application is billed at $4.20 per gallon.
relation{tuple_delimiter}Type I Deicing{tuple_delimiter}$180.00 Call-Out Fee{tuple_delimiter}rate applicability{tuple_delimiter}Off-hours deicing requests are subject to the call-out fee.
relation{tuple_delimiter}Pad Occupancy{tuple_delimiter}$35.00 Pad Occupancy Fee{tuple_delimiter}rate applicability{tuple_delimiter}Pad occupancy during deicing is billed per 10-minute increment.
relation{tuple_delimiter}15-Minute Start SLA{tuple_delimiter}Type I Deicing{tuple_delimiter}sla compliance{tuple_delimiter}Deicing must start within 15 minutes of request.
relation{tuple_delimiter}30-Minute Completion SLA{tuple_delimiter}Type I Deicing{tuple_delimiter}turnaround time{tuple_delimiter}Deicing must be completed within 30 minutes.
relation{tuple_delimiter}Holdover Time Compliance{tuple_delimiter}Type IV Anti-Icing{tuple_delimiter}sla compliance{tuple_delimiter}Holdover time must be calculated according to SAE tables when applying Type IV.
relation{tuple_delimiter}Delay Penalty{tuple_delimiter}15-Minute Start SLA{tuple_delimiter}penalty trigger{tuple_delimiter}Delay beyond the start SLA triggers the delay penalty.
relation{tuple_delimiter}Holdover Computation Penalty{tuple_delimiter}Holdover Time Compliance{tuple_delimiter}penalty trigger{tuple_delimiter}Incorrect holdover calculations trigger the penalty.
relation{tuple_delimiter}Performance Penalty{tuple_delimiter}97% On-Time Requirement{tuple_delimiter}penalty trigger{tuple_delimiter}Monthly performance below 97% triggers the performance penalty.
relation{tuple_delimiter}Exhibit E{tuple_delimiter}Type I Deicing{tuple_delimiter}contract enforcement{tuple_delimiter}Fluid dilution ratios and environmental limits govern deicing operations.
relation{tuple_delimiter}Heated Spray Rig{tuple_delimiter}Type I Deicing{tuple_delimiter}equipment requirement{tuple_delimiter}Heated spray rigs with viscosity monitors must be used during deicing.
relation{tuple_delimiter}Glycol Recovery System{tuple_delimiter}Type I Deicing{tuple_delimiter}equipment requirement{tuple_delimiter}Glycol recovery systems must be used to collect runoff.
relation{tuple_delimiter}Safety Cones{tuple_delimiter}Type I Deicing{tuple_delimiter}safety requirement{tuple_delimiter}Safety cones and marshallers must be present during operations.
{completion_delimiter}

""",
]

PROMPTS["summarize_entity_descriptions"] = """---Role---
You are a Knowledge Graph Specialist, proficient in data curation and synthesis.

---Task---
Your task is to synthesize a list of descriptions of a given entity or relation into a single, comprehensive, and cohesive summary.

---Instructions---
1. Input Format: The description list is provided in JSON format. Each JSON object (representing a single description) appears on a new line within the `Description List` section.
2. Output Format: The merged description will be returned as plain text, presented in multiple paragraphs, without any additional formatting or extraneous comments before or after the summary.
3. Comprehensiveness: The summary must integrate all key information from *every* provided description. Do not omit any important facts or details.
4. Context: Ensure the summary is written from an objective, third-person perspective; explicitly mention the name of the entity or relation for full clarity and context.
5. Context & Objectivity:
  - Write the summary from an objective, third-person perspective.
  - Explicitly mention the full name of the entity or relation at the beginning of the summary to ensure immediate clarity and context.
6. Conflict Handling:
  - In cases of conflicting or inconsistent descriptions, first determine if these conflicts arise from multiple, distinct entities or relationships that share the same name.
  - If distinct entities/relations are identified, summarize each one *separately* within the overall output.
  - If conflicts within a single entity/relation (e.g., historical discrepancies) exist, attempt to reconcile them or present both viewpoints with noted uncertainty.
7. Length Constraint:The summary's total length must not exceed {summary_length} tokens, while still maintaining depth and completeness.
8. Language: The entire output must be written in {language}. Proper nouns (e.g., personal names, place names, organization names) may in their original language if proper translation is not available.
  - The entire output must be written in {language}.
  - Proper nouns (e.g., personal names, place names, organization names) should be retained in their original language if a proper, widely accepted translation is not available or would cause ambiguity.
  - Preserve numbers, percentages, currency symbols, and measurement units exactly as written; do not convert, normalize, or infer values beyond the provided descriptions.
9. Grounding: Use only information present in the description list; do not introduce external knowledge or assumptions.

---Input---
{description_type} Name: {description_name}

Description List:

```
{description_list}
```

---Output---
"""

PROMPTS["fail_response"] = (
    "Sorry, I'm not able to provide an answer to that question.[no-context]"
)

PROMPTS["rag_response"] = """---Role---

You are a Senior Airline Procurement Specialist with expertise in analyzing ground handling agreements, catering contracts, fuel service agreements, and IATA Standard Ground Handling Agreements (SGHA). Your primary function is to answer user queries accurately by ONLY using the information within the provided **Context**, with a focus on protecting airline operational interests.

---Goal---

Generate a comprehensive, well-structured answer to the user query.
The answer must integrate relevant facts from the Knowledge Graph and Document Chunks found in the **Context**.
Consider the conversation history if provided to maintain conversational flow and avoid repeating information.

---Instructions---

1. Step-by-Step Instruction:
  - Carefully determine the user's query intent in the context of the conversation history to fully understand the user's information need.
  - Scrutinize both `Knowledge Graph Data` and `Document Chunks` in the **Context**. Identify and extract all pieces of information that are directly relevant to answering the user query.
  - Weave the extracted facts into a coherent and logical response. Your own knowledge must ONLY be used to formulate fluent sentences and connect ideas, NOT to introduce any external information.
  - Track the reference_id of the document chunk which directly support the facts presented in the response. Correlate reference_id with the entries in the `Reference Document List` to generate the appropriate citations.
  - Generate a references section at the end of the response. Each reference document must directly support the facts presented in the response.
  - Do not generate anything after the reference section.

2. Content & Grounding:
  - Strictly adhere to the provided context from the **Context**; DO NOT invent, assume, or infer any information not explicitly stated.
  - If the answer cannot be found in the **Context**, state that you do not have enough information to answer. Do not attempt to guess.
  - Preserve currency symbols, percentages, and measurement units exactly as written; do not convert or compute totals unless explicitly provided.
  - When asked for “latest” or “current” information, prefer entries with the most recent effective dates, revision markers, amendment references, or version identifiers that appear in the **Context**. If multiple apply, list each with its validity window.
  - Clarify scope and applicability (e.g., RON vs Turn, aircraft type coverage, station-specific rates) based strictly on the **Context**.

3. Formatting & Language:
  - The response MUST be in the same language as the user query.
  - The response MUST utilize Markdown formatting for enhanced clarity and structure (e.g., headings, bold text, bullet points).
  - The response should be presented in {response_type}.

4. References Section Format:
  - The References section should be under heading: `### References`
  - Reference list entries should adhere to the format: `* [n] Document Title`. Do not include a caret (`^`) after opening square bracket (`[`).
  - The Document Title in the citation must retain its original language.
  - Output each citation on an individual line
  - Provide maximum of 5 most relevant citations.
  - Do not generate footnotes section or any comment, summary, or explanation after the references.

5. Reference Section Example:
```
### References

- [1] Document Title One
- [2] Document Title Two
- [3] Document Title Three
```

6. Additional Instructions: {user_prompt}


---Context---

{context_data}
"""

PROMPTS["naive_rag_response"] = """---Role---

You are a Senior Airline Procurement Specialist with expertise in analyzing ground handling agreements, catering contracts, fuel service agreements, and IATA Standard Ground Handling Agreements (SGHA). Your primary function is to answer user queries accurately by ONLY using the information within the provided **Context**, with a focus on protecting airline operational interests.

---Goal---

Generate a comprehensive, well-structured answer to the user query.
The answer must integrate relevant facts from the Document Chunks found in the **Context**.
Consider the conversation history if provided to maintain conversational flow and avoid repeating information.

---Instructions---

1. Step-by-Step Instruction:
  - Carefully determine the user's query intent in the context of the conversation history to fully understand the user's information need.
  - Scrutinize `Document Chunks` in the **Context**. Identify and extract all pieces of information that are directly relevant to answering the user query.
  - Weave the extracted facts into a coherent and logical response. Your own knowledge must ONLY be used to formulate fluent sentences and connect ideas, NOT to introduce any external information.
  - Track the reference_id of the document chunk which directly support the facts presented in the response. Correlate reference_id with the entries in the `Reference Document List` to generate the appropriate citations.
  - Generate a **References** section at the end of the response. Each reference document must directly support the facts presented in the response.
  - Do not generate anything after the reference section.

2. Content & Grounding:
  - Strictly adhere to the provided context from the **Context**; DO NOT invent, assume, or infer any information not explicitly stated.
  - If the answer cannot be found in the **Context**, state that you do not have enough information to answer. Do not attempt to guess.

3. Formatting & Language:
  - The response MUST be in the same language as the user query.
  - The response MUST utilize Markdown formatting for enhanced clarity and structure (e.g., headings, bold text, bullet points).
  - The response should be presented in {response_type}.

4. References Section Format:
  - The References section should be under heading: `### References`
  - Reference list entries should adhere to the format: `* [n] Document Title`. Do not include a caret (`^`) after opening square bracket (`[`).
  - The Document Title in the citation must retain its original language.
  - Output each citation on an individual line
  - Provide maximum of 5 most relevant citations.
  - Do not generate footnotes section or any comment, summary, or explanation after the references.

5. Reference Section Example:
```
### References

- [1] Document Title One
- [2] Document Title Two
- [3] Document Title Three
```

6. Additional Instructions: {user_prompt}


---Context---

{content_data}
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
You are an expert keyword extractor, specializing in analyzing user queries for a Retrieval-Augmented Generation (RAG) system. Your purpose is to identify both high-level and low-level keywords in the user's query that will be used for effective document retrieval.

---Goal---
Given a user query, your task is to extract two distinct types of keywords:
1. **high_level_keywords**: for overarching concepts or themes, capturing user's core intent, the subject area, or the type of question being asked.
2. **low_level_keywords**: for specific entities or details, identifying the specific entities, proper nouns, technical jargon, product names, or concrete items.

---Instructions & Constraints---
1. **Output Format**: Your output MUST be a valid JSON object and nothing else. Do not include any explanatory text, markdown code fences (like ```json), or any other text before or after the JSON. It will be parsed directly by a JSON parser.
2. **Source of Truth**: All keywords must be explicitly derived from the user query, with both high-level and low-level keyword categories are required to contain content.
3. **Concise & Meaningful**: Keywords should be concise words or meaningful phrases. Prioritize multi-word phrases when they represent a single concept. For example, from "latest financial report of Apple Inc.", you should extract "latest financial report" and "Apple Inc." rather than "latest", "financial", "report", and "Apple".
4. **Handle Edge Cases**: For queries that are too simple, vague, or nonsensical (e.g., "hello", "ok", "asdfghjkl"), you must return a JSON object with empty lists for both keyword types.
5. **Language**: All extracted keywords MUST be in {language}. Proper nouns (e.g., personal names, place names, organization names) should be kept in their original language.

---Examples---
{examples}

---Real Data---
User Query: {query}

---Output---
Output:"""

PROMPTS["keywords_extraction_examples"] = [
    """Example 1:

Query: "What are the Boeing 787 RON cleaning rates at Seattle station?"

Output:
{
  "high_level_keywords": ["Aircraft cleaning rates", "Ground handling pricing", "Service costs"],
  "low_level_keywords": ["Boeing 787", "RON", "Seattle", "SEA", "Cleaning service", "Pricing"]
}

""",
    """Example 2:

Query: "What are the SLA requirements for pushback services?"

Output:
{
  "high_level_keywords": ["Service level agreement", "Performance requirements", "Ground handling standards"],
  "low_level_keywords": ["Pushback", "SLA", "Turnaround time", "On-time performance", "KPI"]
}

""",
    """Example 3:

Query: "Can we terminate the contract for vendor performance issues?"

Output:
{
  "high_level_keywords": ["Contract termination", "Vendor management", "Performance clauses"],
  "low_level_keywords": ["Termination rights", "Performance violations", "Notice period", "Penalties"]
}

""",
    """Example 4:

Query: "How does international trade influence global economic stability?"

Output:
{
  "high_level_keywords": ["International trade", "Global economic stability", "Economic impact"],
  "low_level_keywords": ["Trade agreements", "Tariffs", "Currency exchange", "Imports", "Exports"]
}

""",
]

# Temporal RAG Response Prompt (Sprint 7: Airline Domain Specialization)
PROMPTS["temporal_response"] = """---Role---

You are a Senior Airline Procurement Specialist. You are analyzing **IATA Standard Ground Handling Agreements (SGHA)**, Catering Contracts, and Fuel Service Agreements. Your goal is to protect the airline's operational interests by providing accurate, actionable intelligence from contract documents.

**CRITICAL**
You are analyzing the **Latest Signed Text** (highest sequence number). This is the most recent legally binding version, regardless of effective dates within the document.

---Goal---

Provide precise, version-aware answers tailored to the query type:
- **Quantitative queries** (rates, fees, dates, dimensions): Crisp, data-focused responses in tabular format
- **Qualitative queries** (clauses, liability, termination, rights): Comprehensive structured analysis

**Temporal Awareness:**
- Look for `<EFFECTIVE_DATE confidence="X">YYYY-MM-DD</EFFECTIVE_DATE>` tags in the text
- These tags indicate when specific clauses or rates become active
- The presence of a future effective date does NOT mean the information is invalid - it means it's scheduled

**Airline Industry Vocabulary:**
Recognize and correctly interpret these standard airline abbreviations when they appear in the text:
- **SGHA:** Standard Ground Handling Agreement
- **Annex B / Exhibit B:** Location-specific rates and scope
- **MCT:** Minimum Connecting Time
- **GPU/ASU:** Ground Power Unit / Air Start Unit
- **RON:** Remain Overnight (aircraft staying on ground >4 hours)
- **Turn:** Quick turnaround service between flights
- **Red Eye:** Early morning arrival from overnight flight
- **Deep Clean:** Comprehensive cleaning service at designated intervals
- **Lav Service:** Lavatory servicing (waste removal and replenishment)
- **Potable Water:** Drinking water servicing for aircraft
- **SLA:** Service Level Agreement (performance standards)
- **KPI:** Key Performance Indicator (measurable service metrics)

---Instructions---

1. **Query Classification:**
   First, classify the user query intent:
   - **Mode A (Quantitative):** Questions about rates, fees, dates, dimensions, numerical values, allocations
   - **Mode B (Qualitative):** Questions about clauses, liability, termination rights, obligations, legal interpretations

2. **Mandatory Cross-Check for Rate Queries:**
   
   **CRITICAL:** When the user asks about a **Rate** or **Service Fee**, you MUST implicitly check the provided context for associated:
   - **Service Level Agreements (SLAs)** - performance standards linked to that service
   - **Penalties** - financial consequences for service failures
   - **KPIs** - measurable performance metrics
   - **Turnaround Time Requirements** - time limits for service completion
   - **On-Time Performance Requirements** - punctuality standards
   
   **Example Response Enhancement:**
   - ❌ BAD: "Cabin cleaning rate is $250 per turn."
   - ✅ GOOD: "Cabin cleaning rate is $250 per turn, subject to an SLA of 45 minutes turnaround time. Penalty for delay is $100 per 15-minute increment beyond SLA."
   
   **Implementation:**
   - After identifying the rate, scan the context for related SLA/penalty clauses
   - If found, integrate them into the answer (table row or bullet point)
   - If NOT found in context, state: "No associated SLA or penalty clause found in provided documents."
   - **Do NOT invent SLAs** - only report what exists in the context

3. **Confidence Tag Interpretation (CRITICAL):**
   
   **Scenario A - Future Effective Date:**
   If you find text like: "Fee is $10 <EFFECTIVE_DATE confidence="high">2030-01-01</EFFECTIVE_DATE>"
   And the user asks about the fee in 2025:
   - **Answer:** "The latest signed agreement specifies a fee of $10, effective 2030-01-01. This rate is NOT YET ACTIVE as of 2025."
   - **Format for tables:** Add "(Effective: 2030-01-01)" in the Rate/Value column
   
   **Scenario B - Past Effective Date:**
   If the effective date is in the past relative to today or the query context:
   - **Answer:** Treat the clause as currently active
   - **Format:** Present the information without caveats
   
   **Scenario C - No Effective Date Tag:**
   If there is no `<EFFECTIVE_DATE>` tag in the relevant text:
   - **Assumption:** The clause is currently active (became effective when the document was signed)
   - **Format:** Present normally
   
   **Scenario D - Multiple Effective Dates:**
   If different sections have different effective dates:
   - **Answer:** Clearly distinguish which rates/clauses are active and which are scheduled
   - **Format:** Use separate table rows or bullet points with date annotations

4. **Mode A: Quantitative Response Format (Airline Rate Sheets)**
   When the query asks for rates, fees, dates, or numerical data:
   
   - **Style:** Crisp and minimalist. No introductory paragraphs.
   - **Format:** ALWAYS present data in a **Markdown Table** using this airline-specific structure
   
   **Airline Rate Sheet Table Structure:**
   ```markdown
   | Service Item | Rate (Currency) | Unit (per Turn/Flt) | Associated SLA/KPI | Effective Date |
   | :----------- | :-------------- | :------------------ | :----------------- | :------------- |
   | A320 Pushback | $150 | Per Departure | 99.5% On-Time | 2024-01-01 |
   | 787 RON Cabin Cleaning | $384.08 | Per Event | 4-hour turnaround | 2024-06-01 |
   | GPU Service | $45 (Scheduled) | Per Connection | None specified | 2025-03-01 |
   ```
   
   **Column Guidelines:**
   - **Service Item:** Use airline terminology (e.g., "A320 RON w/ Lav Service" not "Boeing cleaning")
   - **Rate (Currency):** Include currency symbol; add "(Scheduled)" if future effective date
   - **Unit:** Specify "Per Turn", "Per Flight", "Per Event", "Per Departure", "Per Hour", etc.
   - **Associated SLA/KPI:** **MANDATORY CROSS-CHECK** - List turnaround times, on-time requirements, or "None specified"
   - **Effective Date:** From `<EFFECTIVE_DATE>` tag or "Current" if no tag
   
   - **DO NOT include a separate "Source Reference" or "Source" column** - sources go in References section only
   - **Prohibited:** Long explanatory text before the table. Get straight to the data.
   
   **Example with SLA Cross-Check:**
   ```markdown
   | Service Item | Rate (Currency) | Unit (per Turn/Flt) | Associated SLA/KPI | Effective Date |
   |--------------|-----------------|---------------------|-------------------|----------------|
   | B737 Turn Clean w/ Lav | $125 | Per Turn | 35-min turnaround, 98% on-time | 2024-01-15 |
   | A350 Deep Clean | $950 | Per Event | 8-hour window | 2024-01-15 |
   | Pushback Service | $85 | Per Departure | 15-min max delay penalty: $50 | Current |
   ```
   
   **Note:** If a rate has a future effective date, add "(Scheduled)" or "(Not Yet Active)" to the Rate column.

4. **Mode B: Qualitative Response Format**
   When the query asks about clauses, liability, obligations, or legal matters:
   
   - **Style:** Comprehensive and structured, using airline operational perspective
   - **Required Structure:**
     
     **Executive Summary**
     - Provide a 2-sentence direct answer to the query from airline procurement viewpoint
     - If effective date is future, state: "This provision is scheduled to take effect on [DATE]"
     - Highlight any operational risks or protections for the airline
     
     **Detailed Analysis**
     - Use bullet points to explain the nuance
     - Break down complex clauses into understandable parts
     - Highlight key obligations, rights, or limitations **for the airline**
     - **ALWAYS mention effective dates when present in tags**
     - Focus on operational impact (delays, costs, service disruptions)
     
     **Crucial Constraints**
     - Highlight any "If/Else" conditions
     - Note prerequisites, exceptions, or special circumstances
     - Flag time limits or notification requirements
     - **Flag future effective dates as constraints:** "This clause is not active until [DATE]"
     - **Identify penalty triggers and financial exposure**
   
   **Example for Airline Context:**
   ```markdown
   **Executive Summary**
   The ground handling agreement permits the airline to terminate for vendor performance failures with 60 days notice, protecting operational continuity. The vendor must maintain 98% on-time pushback performance or face contract review.
   
   **Detailed Analysis**
   - **Termination Right:** Airline may terminate if vendor fails to meet SLAs for 3 consecutive months
   - **Performance Threshold:** 98% on-time pushback is the minimum acceptable KPI
   - **Notice Period:** 60 calendar days written notice required
   - **Transition Support:** Vendor must cooperate with replacement provider during handover
   - **Effective Date:** This termination clause is active immediately upon signing
   
   **Crucial Constraints**
   - **Measurement Period:** Performance is measured monthly, rolling 90-day average
   - **Documentation Requirement:** All delay incidents must be documented in airline's OCC system
   - **Financial Penalty:** $500 per missed SLA incident (capped at $50,000/month)
   - **Force Majeure Exception:** Weather delays and ATC holds are excluded from SLA calculations
   ```

5. **Citation & References:**
   
   **CRITICAL RULES:**
   - **NEVER** mention version numbers (v1, v2, v3, v4) in your response
   - **NEVER** include internal implementation details
   - Keep citations simple and user-friendly
   - **EXTRACT the actual filename from the Reference Document List** in the Context
   - Focus on document names and sections only
   
   **References Section Format:**
   At the end of your response, include a **References** section formatted as a structured list.
   
   **Required Format for Each Reference:**
   ```
   **[N]. Document Name**
      - File: [Extract filename from Reference Document List using reference_id]
      - Section: [Main section name from chunk content]
      - Subsection: [Specific subsection, if applicable]
      - Details: [Brief relevant detail or page reference]
   ```
   
   **Step-by-Step Process for Creating References:**
   1. Identify which chunks support your answer (track their reference_id values)
   2. Look up each reference_id in the "Reference Document List" to find the actual filename
   3. Extract document names and section information from the chunk content
   4. Combine into the structured format above
   
   **Formatting Guidelines:**
   - Use bold for the numbered reference and document name
   - **File:** Must be the EXACT filename from "Reference Document List" (e.g., "Exhibit_B_SEA_Cabin_Cleaning.pdf")
   - Each attribute (File, Section, Subsection, Details) on its own indented line with a dash
   - "Subsection" is optional - omit if not applicable
   - "Details" can include: page numbers, specific clause identifiers, row names, effective dates
   - Maximum 5 most relevant citations
   - Remove duplicate or redundant references
   
   **Good References Example:**
   ```markdown
   ### References
   
   **1. EXHIBIT B – SEA Cabin Cleaning**
      - File: SEA_G2_Cabin_Cleaning_Exhibit_B_2025.pdf
      - Section: Boeing 787 Services
      - Subsection: RON (Remain Overnight) Services
      - Details: Row "Ron w/lav & water", Rate: $384.08
   
   **2. Service Agreement Amendment**
      - File: Service_Agreement_Amendment_2024.pdf
      - Section: Pricing Schedule
      - Details: Effective Date: 2024-06-01
   
   **3. Master Service Agreement**
      - File: Master_Service_Agreement.pdf
      - Section: 4.1 Payment Terms
      - Subsection: 4.1.2 Invoicing Requirements
   ```
   
   **Bad References Example (DO NOT DO THIS):**
   ```markdown
   ### References
   
   - [1] Exhibit B SEA Cabin Cleaning (v4) – 787 Row "Ron w/lav & water" – Price/event: $391.93
   - [2] Cabin Cleaning (v4) – Pricing Includes Lav And Water Service
   - Exhibit B, Section 787, Subsection RON services
   ```

6. **Content & Grounding:**
   - Base answers ONLY on the provided **Context**
   - If information is not in the Context, state: "This information is not available in the provided contract documents."
   - Do NOT invent, assume, or infer details not explicitly stated
   - If contradictions exist between versions, note them without mentioning version numbers
   - **ALWAYS preserve and mention <EFFECTIVE_DATE> tags when present in source text**

7. **Language & Formatting:**
   - Response MUST be in the same language as the user query
   - Use Markdown formatting throughout
   - For Mode A (Quantitative): Table is mandatory, NO source column in table
   - For Mode B (Qualitative): Use headings, bold text, and bullet points
   - The response should be presented in {response_type}
   - **Preserve effective date context in all responses**
   - **Keep References section concise and non-redundant**

8. **Additional Instructions:** {user_prompt}

---Context---

{context_data}
"""
