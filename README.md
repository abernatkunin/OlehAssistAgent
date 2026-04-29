# OlehAssist 🇮🇱

An AI-powered conversational agent designed to help new immigrants (Olim) navigate Israeli bureaucracy.

## 🎯 Overview

OlehAssist leverages Google Cloud Platform's Vertex AI and generative AI models to provide immediate, multilingual guidance for new immigrants to Israel. The agent helps with everything from opening bank accounts to understanding government documents and scheduling essential appointments.

**Live Demo:** [https://olehassist.streamlit.app](https://olehassist.streamlit.app)

## ✨ Key Features

- **Multilingual Support**: Communicates in English, Hebrew, Russian, French, Spanish, and German
- **Retrieval-Augmented Generation (RAG)**: Grounds responses in official Ministry of Aliyah documentation
- **Document Analysis**: Uses multimodal AI to explain government forms, bills, and letters
- **Text-to-SQL**: Queries BigQuery database to find local Ministry of Aliyah branch contact information
- **Smart Routing**: Prompt engineering with function calling to intelligently route users to appropriate resources

## 🛠️ Technologies Used

- **Google Cloud Platform**
  - Vertex AI (Gemini models)
  - BigQuery (structured data queries)
  - Cloud Discovery Engine (RAG implementation)
- **Streamlit** (User Interface)
- **Python** (Core implementation)

## 📋 Three Main Pathways

### 1. General Information (RAG)
Answers questions about rights, benefits, procedures using official Ministry of Aliyah documentation.

### 2. Document Understanding (Multimodal AI)
Upload confusing documents (bills, forms, letters) and receive structured explanations with action steps.

### 3. First Steps & Appointments (Text-to-SQL)
Sequential guidance through critical onboarding tasks:
- Getting an Israeli phone plan
- Opening a bank account
- Scheduling Ministry of Aliyah appointment

## 🚀 Getting Started

```bash
# Clone the repository
git clone https://github.com/abernatkunin/OlehAssistAgent.git
cd OlehAssistAgent

# Install dependencies
pip install -r requirements.txt

# Run locally
streamlit run app.py
```

## 🙏 Acknowledgments

Built as part of the Generative AI course at Reichman University's Lauder School of Government, Diplomacy and Strategy.

## 📝 License

This project was created for educational purposes.
