# Novatrix Azure-Uppgift-6

## Mål och resultat

Koppla det befintliga ärendeformuläret i Azure till Microsoft 365. Ett verkligt testärende med bilaga har sparats av Azure-appen, skapats i SharePoint och gett både Outlook-mejl och Teams-notis. Samma ärendenummer har verifierats i alla delar. Flödeskörningen lyckades och SharePoint visar Ja för båda notiserna. VG omfattar flera sammankopplade tjänster samt motivering och förslag till utökning.

## Lösning

```text
Formulär -> Python API -> privat Blob Storage
                  |
                  +-> beständig lokal kö -> Power Automate
                                          -> SharePoint-post
                                          -> Outlook-mejl
                                          -> Teams-notis
                                          -> uppdatera notisstatus
```

API:t sparar ärende och bilaga innan det lägger ärendet i en SQLite-kö. Servern anropar Power Automate över HTTPS. HTTP 202 betyder mottaget för behandling, inte att alla efterföljande steg är färdiga. Formuläret visar därför att notisen väntar på behandling.

Azure och Microsoft 365 ligger i olika kataloger. Serverns privata anropsadress kopplar samman dem; ingen Azure-prenumeration flyttas. Bilagans namn skickas till SharePoint, men själva filen stannar i privat Blob Storage. Notiserna innehåller bara ärendenummer och en länk till registret.

## Filer

| Fil | Innehåll |
| --- | --- |
| `v39/app/` | Formulär, API, privat lagring, lokal notiskö och serverkonfiguration. |
| `v39/scripts/deploy-app.py` | Installerar appen via Azure Run Command och frigör normalt VM:n efteråt. |
| `v39/flow/definition.example.json` | Export av det körda flödets definition, med miljövärden ersatta av exempelvärden. |
| `v39/flow/request.schema.json` | Ärendedata som HTTP-triggern tar emot. |
| `v39/flow/request.example.json` | Påhittade testdata. |
| `v39/flow/config.example.json` | Mall för lokal, hemlig anropsadress. |
| `v39/sharepoint/list.schema.json` | Beskrivning av listans kolumner; inte verifierat som ett körbart API-skript. |

## Förutsättningar och körning

Azure-miljön från tidigare uppgifter behöver VM, nätverk, privat lagring och appens begränsade skrividentitet. Microsoft 365 Business Basic med Teams samt Power Automate Premium har använts som provperioder. Licenser och anslutningar behöver finnas i den egna miljön.

1. Skapa SharePoint-listan Ärenderegister med kolumnerna i listbeskrivningen. Behåll Title som Rubrik. TicketId ska vara obligatoriskt, unikt och indexerat. TeamsNotified och MailNotified börjar med Nej.
2. Bygg flödet enligt definitionen och koppla SharePoint, Outlook och Teams till ditt eget arbetskonto. Ersätt YOUR_TENANT, YOUR_LIST_ID, YOUR_TEAM_ID, YOUR_CHANNEL_ID och mejlmottagaren. JSON-filen är en referensdefinition, inte ett färdigt importpaket.
3. HTTP-triggern använder Anyone med en signerad, hemlig anropsadress. Begränsa samtidiga körningar till en. Spara adressen endast i en privat lokal JSON-fil enligt config.example.json.
4. Återskapa den privata lagringsanslutningen från uppgift 4 före installation och test. Installera appen med kommandot nedan. Azure CLI ska vara installerat och inloggat i rätt prenumeration.

```text
python v39/scripts/deploy-app.py --resource-group rg-novatrix --storage-account YOUR_STORAGE_ACCOUNT --private-config /private/flow.local.json
```

För ett kort formulärtest kan `--keep-running-for-test` användas. Frigör sedan VM:n själv och ta bort privat endpoint och dess DNS-länk/zon. Standardläget i skriptet frigör VM:n även om installationen misslyckas.

## Flödets steg

1. HTTP-trigger tar emot JSON enligt schemat.
2. Get items söker `TicketId eq '<id>'`, högst en post.
3. Condition kontrollerar att antalet träffar är noll.
4. Om posten saknas: Create item -> Send an email (V2) -> Post message in a chat or channel -> Update item. Sista steget sätter båda notisfälten till Ja.
5. Om posten redan finns: grenen är tom och körningen avslutas utan nya notiser.

## Verifiering

Testärende: `16a7701375e54ec489128f2e998c83d3`.

| Kontroll | Resultat |
| --- | --- |
| Verkligt Azure-formulär med textbilaga | Sparandet lyckades och ärendenummer visades. |
| Power Automate | Hela körningen Succeeded. |
| SharePoint | Samma id, testuppgifter och blobnamn; båda notisfälten Ja. |
| Teams Kundtjänst | Notis med samma ärendenummer levererad. |
| Outlook | Mejl med samma ärendenummer finns i inkorgen. |
| Samma HTTP-anrop igen | Körningen lyckades; listan hade fortfarande bara en post för testärendet och Teams ingen extra notis. |
| Avslut | VM frigjord och den tillfälliga privata anslutningen borttagen. |

Bildbevis och offentlig rapport hålls separat från detta repo. Ett tidigare separat flödestest syns också i registret; dess bilagereferens var testdata och bevisar inte lagring av en faktisk bilaga.

## VG: design och utveckling

SharePoint samlar ärendena. Outlook och Teams gör kundtjänst uppmärksam på samma ärende. Ett gemensamt id gör kedjan enkel att följa. Serverkön försöker igen om HTTP-anropet inte kan bekräftas. Unikt TicketId och en körning åt gången minskar risken för dubbletter.

Kedjan kan utökas med ansvarig handläggare, uppföljning, eskalering och separat återförsök per notis. Detta är förslag, inte delar som redan har byggts.

## Begränsningar och säkerhet

- Om flödet misslyckas efter att SharePoint-posten skapats fortsätter ett nytt anrop inte automatiskt från den misslyckade notisen. Felsök körhistoriken och återställ eller komplettera notisen kontrollerat. Exakt en leverans garanteras inte.
- Notisflaggorna uppdateras tillsammans efter båda notiserna. Vid ett avbrott kan en notis ha skickats även om flaggorna fortfarande är Nej.
- Blob-lagring och den lokala kön ingår inte i en gemensam transaktion. Om köskrivningen misslyckas kan ett sparat ärende behöva skickas till flödet manuellt.
- HTTP-formuläret är en labb utan TLS och kundinloggning. Använd enbart påhittade uppgifter. Verklig användning kräver ytterligare skydd.
- Den som har hela signerade anropsadressen kan starta flödet. Den ligger endast i privat konfiguration och på servern, aldrig i frontend eller repo. Azure-administratörer kan se Run Command-underlaget vid installation.
- Kön innehåller ärendedata på serverns disk. Katalogen skyddas med rättigheter 0700 och tjänstens konto.

## Kostnad

Starta VM och privat anslutning bara när labben används. Disk, IP och lagring kan fortfarande kosta. Provperioderna för Microsoft 365 och Power Automate har fortfarande automatisk förnyelse aktiverad; den måste hanteras separat för att undvika framtida licenskostnader. En budget är en varning, inte en kostnadsspärr.

Kodunderlaget är klart för granskning. PDF, råa bevis, privata inställningar, lösenord och interna arbetsfiler ska inte publiceras i GitHub.
