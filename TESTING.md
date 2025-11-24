# Testing the Document Fetching Service

This guide will help you test the document parsing functionality.

## Prerequisites

1. Make sure Docker containers are running:
   ```bash
   docker compose up -d
   ```

2. Ensure migrations are applied:
   ```bash
   docker compose exec web python manage.py migrate
   ```

## Step 1: Create a ParserType

You need to create a parser type first. You can do this via Django admin or Django shell.

### Option A: Via Django Admin (Recommended)

1. Create a superuser if you haven't already:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

2. Access the admin at: http://localhost:8000/admin/

3. Go to **Parser Types** → **Add Parser Type**
   - **Name**: `Ginnie Mae`
   - **Slug**: `ginnie-mae` (will auto-populate from name)
   - **Active**: ✓ (checked)
   - Click **Save**

### Option B: Via Django Shell

```bash
docker compose exec web python manage.py shell
```

Then run:
```python
from documents.models import ParserType

parser_type = ParserType.objects.create(
    name='Ginnie Mae',
    slug='ginnie-mae',
    active=True
)
print(f"Created parser type: {parser_type}")
exit()
```

## Step 2: Create a DocumentSource

### Option A: Via Django Admin

1. Go to **Document Sources** → **Add Document Source**
   - **Name**: `Ginnie Mae MBS Guide`
   - **Index URL**: `https://www.ginniemae.gov/issuers/program_guidelines/Pages/MBSGuideLib.aspx`
   - **Parser Type**: Select "Ginnie Mae (ginnie-mae)"
   - **Active**: ✓ (checked)
   - Click **Save**

2. **Note the ID** of the created DocumentSource (shown in the list view)

### Option B: Via Django Shell

```bash
docker compose exec web python manage.py shell
```

Then run:
```python
from documents.models import DocumentSource, ParserType

parser_type = ParserType.objects.get(slug='ginnie-mae')
source = DocumentSource.objects.create(
    name='Ginnie Mae MBS Guide',
    index_url='https://www.ginniemae.gov/issuers/program_guidelines/Pages/MBSGuideLib.aspx',
    parser_type=parser_type,
    active=True
)
print(f"Created document source: {source} (ID: {source.id})")
exit()
```

## Step 3: Run the Fetch Command

Now you can test the parsing! Replace `1` with your DocumentSource ID:

```bash
docker compose exec web python manage.py fetch_documents 1
```

### With PDF Hash Calculation (Slower but More Accurate)

If you want to fetch PDFs and calculate hashes (this is slower):

```bash
docker compose exec web python manage.py fetch_documents 1 --fetch-pdfs
```

## Step 4: Check the Results

### Expected Output

You should see output like:
```
Processing source: Ginnie Mae MBS Guide (ID: 1)
Index URL: https://www.ginniemae.gov/issuers/program_guidelines/Pages/MBSGuideLib.aspx
Parser: ginnie-mae

Processing complete!
Documents created: 37
Documents updated: 0
Versions created: 37
```

### Verify in Django Admin

1. Go to http://localhost:8000/admin/
2. Check **Documents** - you should see all the chapters
3. Check **Document Versions** - you should see the PDF versions

### Verify via Django Shell

```bash
docker compose exec web python manage.py shell
```

```python
from documents.models import Document, DocumentVersion, DocumentSource

source = DocumentSource.objects.get(name='Ginnie Mae MBS Guide')
print(f"Source: {source.name}")
print(f"Documents: {source.documents.count()}")
print(f"Versions: {DocumentVersion.objects.filter(document__source=source).count()}")

# List first few documents
for doc in source.documents.all()[:5]:
    print(f"  - {doc.title} ({doc.slug})")
    print(f"    Versions: {doc.versions.count()}")
```

## Troubleshooting

### Error: "DocumentSource with id X does not exist"
- Make sure you're using the correct ID
- Check in admin: http://localhost:8000/admin/documents/documentsource/

### Error: "Failed to fetch index page"
- Check your internet connection
- Verify the URL is accessible
- Check Docker logs: `docker-compose logs web`

### No documents created
- Check the parser type slug matches (should be `ginnie-mae`)
- Verify the HTML structure hasn't changed
- Check for errors in the output

### View Logs
```bash
docker compose logs -f web
```

## Quick Test Script

You can also use this quick setup script:

```bash
docker compose exec web python manage.py shell << EOF
from documents.models import ParserType, DocumentSource

# Create parser type
parser_type, created = ParserType.objects.get_or_create(
    slug='ginnie-mae',
    defaults={'name': 'Ginnie Mae', 'active': True}
)
print(f"Parser type: {parser_type} (created: {created})")

# Create document source
source, created = DocumentSource.objects.get_or_create(
    name='Ginnie Mae MBS Guide',
    defaults={
        'index_url': 'https://www.ginniemae.gov/issuers/program_guidelines/Pages/MBSGuideLib.aspx',
        'parser_type': parser_type,
        'active': True
    }
)
print(f"Document source: {source} (ID: {source.id}) (created: {created})")
EOF
```

Then run:
```bash
docker compose exec web python manage.py fetch_documents 1
```

