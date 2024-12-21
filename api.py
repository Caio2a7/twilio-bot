import os
from flask import Flask, request, jsonify
from google.cloud import vision
from google.cloud import storage
from twilio.twiml.messaging_response import MessagingResponse
import requests
import json
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Configuração da autenticação
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'chave.json'

# Inicializa o cliente da API do Google Vision
vision_client = vision.ImageAnnotatorClient()
storage_client = storage.Client()

# Função para processar o PDF
def process_pdf(pdf_path):
    # Enviar o PDF para o Google Cloud Storage
    bucket_name = 'seu-bucket-name'
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(os.path.basename(pdf_path))
    blob.upload_from_filename(pdf_path)

    # Usar o Google Vision API para interpretar o documento
    gcs_source = f'gs://{bucket_name}/{os.path.basename(pdf_path)}'
    input_config = vision.InputConfig(
        gcs_source=vision.GcsSource(uri=gcs_source),
        mime_type='application/pdf'
    )
    request = vision.AnnotateFileRequest(input_config=input_config)

    response = vision_client.batch_annotate_files(requests=[request])
    annotations = response.responses

    extracted_data = {}
    for page in annotations:
        for entity in page.text_annotations:
            # Extraindo campos específicos. Adapte conforme necessário.
            if "Nome" in entity.description:
                extracted_data['nome'] = entity.description
            if "Data" in entity.description:
                extracted_data['data'] = entity.description
            # Adicione mais campos conforme a necessidade.

    return extracted_data

# Função para responder via Twilio WhatsApp
def send_whatsapp_response(from_number, response_message):
    twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER')

    url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_account_sid}/Messages.json"
    payload = {
        'To': from_number,
        'From': twilio_phone_number,
        'Body': response_message
    }
    headers = {
        'Authorization': f'Basic {twilio_account_sid}:{twilio_auth_token}'
    }
    
    response = requests.post(url, data=payload, headers=headers)
    return response

# Endpoint para detectar texto em imagem
@app.route('/detect-text', methods=['POST'])
def detect_text():
    content = request.files['image'].read()
    image = vision.Image(content=content)
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations
    return jsonify([text.description for text in texts])

# Endpoint para receber o PDF via WhatsApp
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.form  # Twilio envia dados no formato form-urlencoded
    print("Dados recebidos:", data)  # Adicionando esta linha para imprimir os dados
    media_url = data.get('MediaUrl0')  # URL do PDF enviado
    from_number = data.get('From')  # Número do remetente

    # Imprimir os dados recebidos para depuração

    if media_url:
        pdf_path = 'temp.pdf'  # Caminho temporário para armazenar o PDF

        # Faça o download do PDF
        response = requests.get(media_url)
        with open(pdf_path, 'wb') as f:
            f.write(response.content)

        # Processa o PDF e extrai dados
        extracted_data = process_pdf(pdf_path)

        # Formata resposta
        json_response = json.dumps(extracted_data)

        # Enviar resposta via WhatsApp usando Twilio
        send_whatsapp_response(from_number, json_response)
    else:
        # Imprimir a mensagem se não houver PDF
        print("Mensagem recebida:", data)


    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(port=5000)
