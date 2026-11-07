package cqa.api;

import cqa.api.ApiModels.*;
import cqa.dataset.Dataset;
import cqa.dto.Checklist;
import cqa.service.*;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping(value="/api", produces="application/json")
public class ResourceController {
    private final RequestBodies bodies;
    private final ConversationService conversations;
    private final ChecklistService checklists;
    private final EvaluationService evaluations;
    public ResourceController(RequestBodies bodies, ConversationService conversations, ChecklistService checklists, EvaluationService evaluations) {
        this.bodies=bodies; this.conversations=conversations; this.checklists=checklists; this.evaluations=evaluations;
    }
    @PostMapping(value="/datasets/import", consumes="application/json")
    public Dataset.ImportResult importDataset(HttpServletRequest request) { return conversations.importDataset(bodies.read(request, Dataset.Envelope.class)); }
    @GetMapping("/conversations") public List<Dataset.Summary> conversations() { return conversations.list(); }
    @GetMapping("/conversations/{id}") public Dataset.Conversation conversation(@PathVariable String id) { return conversations.get(id); }
    @GetMapping("/checklists") public List<Checklist> checklists() { return checklists.list(); }
    @GetMapping("/checklists/{key}") public Checklist checklist(@PathVariable String key, @RequestParam(required=false) String version) {
        return checklists.get(key, RequestBodies.version(version, false));
    }
    @PostMapping(value="/checklists/{key}", consumes="application/json")
    public Checklist createChecklist(@PathVariable String key, HttpServletRequest request) { return checklists.create(key, bodies.read(request, ChecklistDraft.class)); }
    @PutMapping(value="/checklists/{key}", consumes="application/json")
    public Checklist updateChecklist(@PathVariable String key, @RequestParam(name="expected_version",required=false) String expected, HttpServletRequest request) {
        return checklists.update(key, RequestBodies.version(expected, true), bodies.read(request, ChecklistDraft.class));
    }
    @PostMapping(value="/evaluations/manual", consumes="application/json") @ResponseStatus(HttpStatus.CREATED)
    public EvaluationView manual(HttpServletRequest request) { return evaluations.manual(bodies.read(request, ManualRequest.class)); }
    @GetMapping("/evaluations") public List<EvaluationView> evaluations(@RequestParam(name="conversation_id",required=false) String conversation) { return evaluations.list(conversation); }
    @GetMapping("/evaluations/{id}") public EvaluationView evaluation(@PathVariable String id) { return evaluations.get(id); }
}
