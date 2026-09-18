"""Optional OpenAI Responses adapter for FoodLens's existing grounded chat flow."""
import json
import os
import urllib.error
import urllib.request

from gemini_service import GeminiClient, GeminiError


class OpenAIClient(GeminiClient):
    """Reuse query parsing and citation checks; only the model transport changes."""

    def __init__(self, key=None, model=None, transport=None):
        super().__init__(key=key if key is not None else os.getenv('OPENAI_API_KEY', ''),
                         model=model or os.getenv('OPENAI_ASSISTANT_MODEL', 'gpt-5.6-luna'),
                         transport=transport)

    def _request(self, body):
        schema={**body['response_format']['schema'], 'additionalProperties':False}
        payload={
            'model':self.model,
            'instructions':body['system_instruction'],
            'input':body['input'],
            'text':{'format':{'type':'json_schema','name':'foodlens_answer'
                              if 'CANDIDATES' in body['system_instruction'] else 'foodlens_query',
                              'strict':True,'schema':schema}},
            'reasoning':{'effort':'none'},
            'store':False,
        }
        request=urllib.request.Request('https://api.openai.com/v1/responses',
            data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+self.key},method='POST')
        try:
            with urllib.request.urlopen(request,timeout=20) as response:
                result=json.load(response)
        except urllib.error.HTTPError as exc:
            message={400:'OpenAI từ chối cấu trúc yêu cầu.',401:'OpenAI API key không hợp lệ.',
                     403:'OpenAI API bị từ chối.',429:'OpenAI đã đạt giới hạn sử dụng.'}.get(
                         exc.code,f'OpenAI trả HTTP {exc.code}.')
            raise GeminiError(message) from None
        except (urllib.error.URLError,TimeoutError,ValueError):
            raise GeminiError('Không thể đọc phản hồi OpenAI.') from None
        texts=[part['text'] for item in result.get('output',[]) if item.get('type')=='message'
               for part in item.get('content',[]) if part.get('type')=='output_text' and part.get('text')]
        if not texts:
            raise GeminiError('OpenAI không trả về nội dung hợp lệ.')
        return {'output_text':'\n'.join(texts),'usage':result.get('usage',{})}
