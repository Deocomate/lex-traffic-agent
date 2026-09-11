"""
Lớp Structured Output chịu lỗi cho mô hình ngôn ngữ (LexTraffic AI).
Cung cấp cơ chế gọi có cấu trúc 4 tầng bảo đảm hoạt động ổn định với các mô hình
nhỏ hoặc mô hình trên OpenRouter có khả năng function calling không hoàn hảo.

Tầng 1: model.with_structured_output(Schema, method="json_schema")
Tầng 2: Prompt bổ sung JSON schema + PydanticOutputParser
Tầng 3: Gọi thông thường + trích xuất khối JSON bằng regex + Schema.model_validate
Tầng 4: Trả về None (không bao giờ ném ngoại lệ) -> đồ thị sử dụng đường định tuyến tất định
"""

import contextvars
import json
import logging
import re
from typing import Any, List, Optional, Type, TypeVar, Union

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ContextVar bảo đảm an toàn đa luồng/async cho việc theo dõi tầng thực thi
_last_tier_var: contextvars.ContextVar[int] = contextvars.ContextVar("structured_call_last_tier", default=0)


def get_last_tier() -> int:
    """Lấy tầng structured output được sử dụng gần nhất trong context hiện tại."""
    return _last_tier_var.get()



def _extract_text_from_response(response: Any) -> str:
    """Bóc tách chuỗi văn bản từ phản hồi của mô hình."""
    if hasattr(response, "content"):
        content = response.content
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
            return "".join(parts)
        return str(content)
    return str(response)


def _extract_json_string(text: str) -> Optional[str]:
    """
    Trích xuất chuỗi JSON hợp lệ từ văn bản thô.
    Hỗ trợ cả markdown code block, JSON lẫn văn xuôi, và cấu trúc lồng nhau.
    """
    if not text:
        return None

    # 1. Thử bóc tách từ các khối code block ```json ... ``` hoặc ``` ... ```
    code_block_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    for match in code_block_pattern.finditer(text):
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass

    # 2. Tìm khối ngoặc nhọn { ... } hoặc ngoặc vuông [ ... ] cân bằng
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start_indices = [i for i, c in enumerate(text) if c == start_char]
        for start_idx in start_indices:
            depth = 0
            in_string = False
            escape = False
            for i in range(start_idx, len(text)):
                c = text[i]
                if escape:
                    escape = False
                    continue
                if c == "\\":
                    escape = True
                    continue
                if c == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if c == start_char:
                        depth += 1
                    elif c == end_char:
                        depth -= 1
                        if depth == 0:
                            candidate = text[start_idx : i + 1].strip()
                            try:
                                json.loads(candidate)
                                return candidate
                            except Exception:
                                break

    # 3. Thử regex tìm khối JSON rộng nhất
    regex_candidates = re.findall(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    for cand in regex_candidates:
        cand_strip = cand.strip()
        try:
            json.loads(cand_strip)
            return cand_strip
        except Exception:
            pass

    return None


def _augment_prompt_with_instructions(
    prompt: Any,
    instructions: str,
) -> Any:
    """Gắn chỉ dẫn định dạng JSON vào prompt (hỗ trợ str, list message, và PromptValue)."""
    if isinstance(prompt, str):
        return f"{prompt}\n\n{instructions}"

    # Hỗ trợ PromptValue (như ChatPromptValue, StringPromptValue)
    if hasattr(prompt, "to_messages"):
        messages = list(prompt.to_messages())
        if messages and hasattr(messages[-1], "content"):
            last_msg = messages[-1]
            msg_cls = type(last_msg)
            messages[-1] = msg_cls(content=f"{last_msg.content}\n\n{instructions}")
        else:
            messages.append(HumanMessage(content=instructions))
        prompt_cls = type(prompt)
        try:
            return prompt_cls(messages=messages)
        except Exception:
            return messages

    elif isinstance(prompt, list):
        new_list = list(prompt)
        if new_list and hasattr(new_list[-1], "content"):
            last_msg = new_list[-1]
            msg_cls = type(last_msg)
            new_list[-1] = msg_cls(content=f"{last_msg.content}\n\n{instructions}")
            return new_list
        else:
            new_list.append(HumanMessage(content=instructions))
            return new_list

    return prompt


def structured_call(
    model: Union[Runnable, Any],
    schema: Type[T],
    prompt: Union[str, List[BaseMessage], Any],
    config: Optional[RunnableConfig] = None,
    system_instruction: Optional[str] = None,
    return_tier: bool = False,
    **kwargs: Any,
) -> Any:
    """
    Gọi mô hình ngôn ngữ và chuyển đổi kết quả thành Schema Pydantic theo 4 tầng bảo vệ.

    Args:
        model: Mô hình ngôn ngữ LangChain hoặc Runnable.
        schema: Lớp Pydantic BaseModel định nghĩa cấu trúc dữ liệu đầu ra.
        prompt: Câu nhắc đầu vào (chuỗi, danh sách BaseMessage, hoặc PromptValue).
        config: Cấu hình RunnableConfig tùy chọn của LangChain.
        system_instruction: Lời nhắc hệ thống tùy chọn.
        return_tier: Nếu True, trả về tuple (result, tier_int). Mặc định False -> trả về result.
        **kwargs: Tham số bổ sung chuyển tới model.invoke.

    Returns:
        Instance của schema Pydantic đã validate, hoặc None nếu mọi tầng đều thất bại.
    """
    last_raw_response_text: Optional[str] = None

    def _format_return(val: Optional[T], tier: int) -> Any:
        _last_tier_var.set(tier)
        structured_call.last_tier = tier  # type: ignore[attr-defined]
        try:
            from src.observability.tracer import record_structured_tier

            record_structured_tier(tier, schema.__name__)
        except Exception:
            pass
        if return_tier:
            return val, tier
        return val

    # Chuẩn bị prompt nếu có system_instruction
    current_prompt = prompt
    if system_instruction:
        if isinstance(prompt, str):
            current_prompt = [
                SystemMessage(content=system_instruction),
                HumanMessage(content=prompt),
            ]
        elif isinstance(prompt, list):
            # Nếu chưa có SystemMessage ở đầu, bổ sung vào đầu danh sách
            if not prompt or not isinstance(prompt[0], SystemMessage):
                current_prompt = [SystemMessage(content=system_instruction)] + list(prompt)
        elif hasattr(prompt, "to_messages"):
            msgs = list(prompt.to_messages())
            if not msgs or not isinstance(msgs[0], SystemMessage):
                msgs = [SystemMessage(content=system_instruction)] + msgs
                try:
                    current_prompt = type(prompt)(messages=msgs)
                except Exception:
                    current_prompt = msgs


    # --- TẦNG 1: with_structured_output(schema, method="json_schema") ---
    try:
        logger.debug("structured_call: Đang thử Tầng 1 (with_structured_output json_schema)")
        structured_model = model.with_structured_output(schema, method="json_schema")
        res = structured_model.invoke(current_prompt, config=config, **kwargs)
        if isinstance(res, schema):
            logger.info("structured_call: Tầng 1 thành công cho %s", schema.__name__)
            return _format_return(res, 1)
        elif isinstance(res, dict):
            validated = schema.model_validate(res)
            logger.info("structured_call: Tầng 1 (dict) thành công cho %s", schema.__name__)
            return _format_return(validated, 1)
        elif res is not None:
            validated = schema.model_validate(res)
            logger.info("structured_call: Tầng 1 thành công cho %s", schema.__name__)
            return _format_return(validated, 1)
    except Exception as e1:
        logger.warning(
            "structured_call: Tầng 1 (json_schema) thất bại (%s: %s). Thử fallback function_calling...",
            type(e1).__name__,
            e1,
        )
        try:
            # Thử thêm method mặc định nếu json_schema không được hỗ trợ
            structured_model = model.with_structured_output(schema)
            res = structured_model.invoke(current_prompt, config=config, **kwargs)
            if isinstance(res, schema):
                logger.info("structured_call: Tầng 1b thành công cho %s", schema.__name__)
                return _format_return(res, 1)
            elif isinstance(res, dict):
                validated = schema.model_validate(res)
                logger.info("structured_call: Tầng 1b (dict) thành công cho %s", schema.__name__)
                return _format_return(validated, 1)
        except Exception as e1b:
            logger.warning(
                "structured_call: Tầng 1b thất bại (%s: %s). Chuyển sang Tầng 2.",
                type(e1b).__name__,
                e1b,
            )

    # --- TẦNG 2: Prompt kèm JSON schema + PydanticOutputParser ---
    try:
        logger.debug("structured_call: Đang thử Tầng 2 (PydanticOutputParser)")
        parser = PydanticOutputParser(pydantic_object=schema)
        format_instructions = parser.get_format_instructions()
        augmented_prompt = _augment_prompt_with_instructions(current_prompt, format_instructions)

        response = model.invoke(augmented_prompt, config=config, **kwargs)
        raw_text = _extract_text_from_response(response)
        last_raw_response_text = raw_text

        parsed = parser.parse(raw_text)
        logger.info("structured_call: Tầng 2 thành công cho %s", schema.__name__)
        return _format_return(parsed, 2)
    except Exception as e2:
        logger.warning(
            "structured_call: Tầng 2 thất bại (%s: %s). Chuyển sang Tầng 3.",
            type(e2).__name__,
            e2,
        )

    # --- TẦNG 3: Bóc tách regex JSON + loads + model_validate ---
    try:
        logger.debug("structured_call: Đang thử Tầng 3 (Regex JSON extraction)")
        raw_text = last_raw_response_text
        if not raw_text:
            response = model.invoke(current_prompt, config=config, **kwargs)
            raw_text = _extract_text_from_response(response)

        extracted_json = _extract_json_string(raw_text)
        if extracted_json:
            data = json.loads(extracted_json)
            validated = schema.model_validate(data)
            logger.info("structured_call: Tầng 3 thành công cho %s", schema.__name__)
            return _format_return(validated, 3)
        else:
            logger.warning("structured_call: Tầng 3 không tìm thấy JSON hợp lệ trong phản hồi.")
    except Exception as e3:
        logger.warning(
            "structured_call: Tầng 3 thất bại (%s: %s). Chuyển sang Tầng 4.",
            type(e3).__name__,
            e3,
        )

    # --- TẦNG 4: Trả về None (không ném ngoại lệ) ---
    logger.warning(
        "structured_call: Tầng 4 - Mọi tầng đều thất bại cho schema %s. Trả về None.",
        schema.__name__,
    )
    return _format_return(None, 4)


# Khởi tạo thuộc tính theo dõi tầng được gọi gần nhất
structured_call.last_tier = 0  # type: ignore[attr-defined]
