"""Count source context using the existing model's verified tokenizer assets."""
import hashlib,json
from pathlib import Path


class EvidenceTokenBudget:
    def __init__(self, asset_root, client=None):
        self.root=Path(asset_root);self.verified_model=False;self.reason='model_metadata_not_checked'
        self.template_reserve=256
        from tokenizers import Tokenizer
        path=self.root/'tokenizer.json'
        proof=json.loads((self.root/'PROVENANCE.json').read_text(encoding='utf-8'))
        expected=next(x['sha256'] for x in proof['files'] if x['path']=='tokenizer.json')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Tokenizer asset fingerprint changed')
        self.tokenizer=Tokenizer.from_file(str(path))
        if client is not None:
            response=client._request('/api/show',payload={'model':client.generation_model(),'verbose':True},timeout_seconds=15)
            info=response.get('model_info',{});tokens=info.get('tokenizer.ggml.tokens') or []
            raw=json.loads(path.read_text(encoding='utf-8'))
            vocab=raw['model']['vocab']
            # Padding/vision-only added tokens differ across some GGUF builds.
            # Verify every base BPE token and the chat boundary tokens actually
            # used by this text-only application.
            matches=bool(tokens) and all(i<len(tokens) and tokens[i]==s for s,i in vocab.items())
            official_merges=[' '.join(x) if isinstance(x,list) else x for x in raw['model'].get('merges',[])]
            installed_merges=info.get('tokenizer.ggml.merges') or []
            matches=matches and official_merges==installed_merges
            matches=matches and all(i<len(tokens) and tokens[i]==s for s,i in
                [('<|endoftext|>',151643),('<|im_start|>',151644),('<|im_end|>',151645)])
            template=str(response.get('template') or '')
            self.verified_model=bool(matches and '<|im_start|>' in template and '<|im_end|>' in template)
            self.reason='base_vocabulary_and_chat_boundaries_verified' if self.verified_model else 'installed_tokenizer_not_verified'
            if self.verified_model:
                # Full template token count is conservative for inactive Go
                # branches; actual prompt_eval_count remains the API measure.
                self.template_reserve=max(128,len(self.tokenizer.encode(template,add_special_tokens=False).ids)+64)

    def count(self, text):
        if not self.verified_model:
            return len(text.encode('utf-8'))
        return len(self.tokenizer.encode(text,add_special_tokens=False).ids)

    def measure(self, system, prompt, context_limit, output_reserve):
        content=self.count(system+'\n'+prompt)
        upper=content+self.template_reserve
        return {'content_tokens':content,'prompt_token_upper_bound':upper,
            'method':'verified_Qwen_BPE_plus_template_reserve' if self.verified_model else 'conservative_UTF8_byte_bound',
            'tokenizer_verified_against_installed_model':self.verified_model,
            'tokenizer_verification':self.reason,'template_reserve':self.template_reserve,
            'context_limit':context_limit,'output_reserve':output_reserve,
            'fits':upper+output_reserve<=context_limit,
            'actual_prompt_tokens':'reported separately from Ollama prompt_eval_count'}
