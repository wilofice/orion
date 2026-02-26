FROM public.ecr.aws/lambda/python:3.11
LABEL authors="orionapi"

COPY app/ /var/task/
RUN rm -rf /var/task/htmlcov/
RUN pip install -r /var/task/requirements.txt

CMD ["boot.lambda_handler"]
