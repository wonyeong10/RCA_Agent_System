import json
import transformers
import random
import gc
import torch
import string
import re
import os
import pickle
from tqdm import tqdm



def validate_json_schema(data):
    return 1.0 

def save_reflection_data(reflection):
    with open("reflections.json", "a") as f:
        json.dump(reflection, f)

def Eval_MAS(results, answers):
    assert len(results) == len(answers), "The prediction does not match the actual number of results"

    total_case = len(results)
    correct_count = 0
    partial_count = 0

    for gt, pred in zip(results, answers):
        gt_set = set(gt)
        pred_set = set(pred)

        if gt_set == pred_set:
            correct_count += 1
        elif len(gt_set & pred_set) > 0:
            partial_count += 1

    return {
        "Correct": round(correct_count / total_case * 100, 2),
        "Partial": round(partial_count / total_case * 100, 2),
        "total_case": total_case
    }


def Eval_MAS_single(result, answer):
    pass

def llm_invoke(model, tokenizer, system_prompt, user_prompt, max_token=512, temperature=1, verbose=True):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    model_inputs = tokenizer([text],truncation=True, return_tensors="pt").to(model.device)
    if verbose:
        print(f'The number of input tokens is {model_inputs["input_ids"].numel()}')
    generated_ids = model.generate(
        **model_inputs,
        max_new_tokens=max_token,
        temperature=temperature,
        do_sample=False 
    )

    generated_ids = [
        output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]

    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
    
    return response, text

def llm_invoke_batch(model, tokenizer, system_prompt, user_prompts, max_token=512, temperature=1, batch_size=1, verbose=False):
    all_responses = []

    for i in tqdm(range(0, len(user_prompts), batch_size), desc="Processing batches"):
        batch_user_prompts = user_prompts[i:i+batch_size]
        batch_inputs = []

        for user_prompt in batch_user_prompts:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            batch_inputs.append(text)

        model_inputs = tokenizer(batch_inputs, return_tensors="pt", padding=True, truncation=True).to(model.device)

        if verbose:
            print(f'The number of input tokens is {model_inputs["input_ids"].numel()}')

        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=max_token,
            temperature=temperature,
            do_sample=False 
        )

        generated_ids = [
            output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]

        responses = [
            tokenizer.decode(output_ids, skip_special_tokens=True) for output_ids in generated_ids
        ]
        
        all_responses.extend(responses)

    return all_responses

def generate_random_string(length=8):
    
    characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choices(characters, k=length))
    return random_string

def extract_between_tags(text, tag):
    pattern = rf'<{tag}>(.*?)</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""

def save_pkl(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(data, f)

def load_pkl(path):
    with open(path, 'rb') as f:
        return pickle.load(f)

def llm_invoke_vllm(llm, tokenizer, system_prompt, user_prompt, max_token=512, temperature=1.0, verbose=True):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    if verbose:
        print(f"Prompt Preview:\n{prompt[:200]}...")

    sampling_params = SamplingParams(
        max_tokens=max_token,
        temperature=temperature,
        top_p=0.9,
    )

    outputs = llm.generate([prompt], sampling_params)[0]
    return outputs.outputs[0].text.strip()


def llm_invoke_batch_vllm(llm, tokenizer, system_prompt, user_prompts, max_token=512, temperature=1.0, batch_size=1, verbose=False):
    all_responses = []

    for i in tqdm(range(0, len(user_prompts), batch_size), desc="Processing Batches"):
        batch_user_prompts = user_prompts[i:i+batch_size]
        prompts = []

        for user_prompt in batch_user_prompts:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            prompts.append(prompt)

        sampling_params = SamplingParams(
            max_tokens=max_token,
            temperature=temperature,
            top_p=0.9,
        )

        results = llm.generate(prompts, sampling_params)
        for output in results:
            response = output.outputs[0].text.strip()
            all_responses.append(response)

    return all_responses    

def clear_inference_memory():
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.ipc_collect() 