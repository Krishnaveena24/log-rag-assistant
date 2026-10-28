variable "region" {
  description = "AWS region with Bedrock access"
  type        = string
  default     = "ap-southeast-2"
}

variable "project_name" {
  description = "Name used for the Lambda function and other resources"
  type        = string
  default     = "log-rag-assistant"
}

variable "chat_model_id" {
  description = "Bedrock model (or inference profile) that writes the answer"
  type        = string
  default     = "apac.amazon.nova-micro-v1:0"
}

variable "embed_model_id" {
  description = "Bedrock embedding model used for retrieval"
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}
